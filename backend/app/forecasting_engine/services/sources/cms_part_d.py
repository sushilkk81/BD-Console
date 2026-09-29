"""CMS Medicare Part D Spending by Drug.

COVERAGE, STATED ONCE AND CARRIED EVERYWHERE: this dataset counts drugs prescribed to
beneficiaries enrolled in Medicare Part D and generally self-administered. That is a
covered subpopulation — not the total US market — and nothing here scales it to a
national figure. Applying a coverage factor is a deliberate, documented act by a person.

Spending is CMS's gross drug cost (Medicare + plan + beneficiary payments). CMS is
prohibited from disclosing manufacturer rebates, so it is NOT manufacturer net revenue
and is never offered as one.

Two ingest routes, one parser:
  * the live JSON API, when data.cms.gov is reachable;
  * the official bulk CSV download, for when it is not.
Both resolve their columns from the data actually in front of them rather than from
hardcoded guesses (see resolve_columns), so a CMS column rename surfaces as a loud
configuration error instead of silently wrong numbers.
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import html
import io
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.forecasting_engine.core.units import (ApiConnectivity, FileVerificationStatus,
                                                ProvenanceClass, PublicationFreshness,
                                                SourceKind, SourceMetric)
from app.forecasting_engine.services.sources.base import (BACKOFF_BASE_SECONDS, HTTP_TIMEOUT_SECONDS,
                                                           MAX_ATTEMPTS, MAX_ROWS, Observation,
                                                           SourceSearchResult, SourceStatus)

logger = logging.getLogger("forecasting.cms_part_d")

DESCRIPTOR_PATH = Path(__file__).with_name("cms_part_d_datasets.json")

#: Only these hosts may be contacted. A descriptor pointing anywhere else is rejected.
ALLOWED_HOSTS = frozenset({"data.cms.gov"})

#: Ceiling on an ingested file, checked before parsing.
MAX_FILE_BYTES = 40_000_000

COVERAGE_CAVEAT = (
    "Medicare Part D enrolled beneficiaries only. Not total US market volume; "
    "extrapolating to the US requires an explicit, documented coverage factor."
)

#: The unit each metric is counted in. Deliberately distinct strings: a claim is not a
#: dosage unit and a beneficiary is not an annual treated patient.
METRIC_UNITS = {
    SourceMetric.DOSAGE_UNITS: "dosage_units",
    SourceMetric.CLAIMS: "claims",
    SourceMetric.BENEFICIARIES: "beneficiaries",
    SourceMetric.SPENDING: "currency",
}

#: Values CMS uses for a figure it did not report. These stay NULL, never 0.
NULL_TOKENS = frozenset({"", "*", "na", "n/a", "null", "none", "suppressed", "redacted"})


class DescriptorError(RuntimeError):
    """The dataset descriptor is missing, malformed, unverified or points off-host."""


class ColumnResolutionError(RuntimeError):
    """The data on hand does not carry the columns the descriptor says it should."""


@lru_cache(maxsize=1)
def load_descriptor(path: str | None = None) -> dict:
    target = Path(path) if path else DESCRIPTOR_PATH
    with target.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_descriptor(descriptor: dict) -> dict:
    """Return the verified dataset block, or raise DescriptorError explaining why not."""
    if not descriptor.get("verified"):
        raise DescriptorError(
            "CMS dataset descriptor is not verified. "
            f"{descriptor.get('why_unverified', '')}".strip())
    dataset = descriptor.get("dataset") or {}
    required = {"api_url", "csv_url", "geography", "coverage", "latest_data_year",
                "available_data_years", "brand_name_column", "generic_name_column",
                "manufacturer_column", "manufacturer_total_label",
                "year_suffixed_metric_columns"}
    missing = required - set(dataset)
    if missing:
        raise DescriptorError(f"CMS dataset descriptor is missing: {sorted(missing)}")
    for key in ("api_url", "csv_url"):
        host = urlparse(dataset[key]).hostname
        if host not in ALLOWED_HOSTS:
            raise DescriptorError(f"descriptor {key} resolves to non-allowlisted host {host!r}")
    return dataset


def resolve_columns(available: list[str], dataset: dict, data_year: int) -> dict[SourceMetric, str]:
    """Map each metric to the real column name for one data year.

    `available` is the actual header of the file (or the keys of a real API record), so
    the mapping is confirmed against the data rather than assumed. A metric whose column
    is absent is simply left out; if none resolve at all, that is a configuration error
    and the caller reports it as such.
    """
    present = set(available)
    for name_key in ("brand_name_column", "generic_name_column"):
        if dataset[name_key] not in present:
            raise ColumnResolutionError(
                f"expected column {dataset[name_key]!r} is not in the data "
                f"(saw {sorted(present)[:8]}...)")
    resolved: dict[SourceMetric, str] = {}
    for metric_name, template in (dataset["year_suffixed_metric_columns"] or {}).items():
        try:
            metric = SourceMetric(metric_name)
        except ValueError:
            continue
        column = template.format(year=data_year)
        if column in present:
            resolved[metric] = column
    if not resolved:
        raise ColumnResolutionError(
            f"no metric columns for data year {data_year} are present in the data; "
            f"available years are {dataset.get('available_data_years')}")
    return resolved


def parse_number(raw: object) -> Decimal | None:
    """Parse a CMS value. Suppressed/blank stays None — never coerced to 0."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in NULL_TOKENS:
        return None
    try:
        return Decimal(text.replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return None


def _matches(record: dict, dataset: dict, molecule: str | None, brand: str | None) -> bool:
    generic = str(record.get(dataset["generic_name_column"]) or "").strip().lower()
    brand_name = str(record.get(dataset["brand_name_column"]) or "").strip().lower()
    if brand and brand.lower() not in brand_name:
        return False
    if molecule and molecule.lower() not in generic:
        return False
    return bool(brand or molecule)


def records_to_observations(
    records: list[dict],
    dataset: dict,
    data_year: int,
    *,
    molecule: str | None,
    brand: str | None,
    source_url: str,
    source_identifier: str,
    retrieval_note: str,
    retrieved_at: dt.datetime | None = None,
    provenance_class: ProvenanceClass = ProvenanceClass.LIVE_CMS_API,
    retrieval_url: str | None = None,
    archive_capture_date: dt.datetime | None = None,
    content_sha256: str | None = None,
    file_verification: FileVerificationStatus | None = None,
) -> tuple[list[Observation], list[str]]:
    """Turn matched CMS records into Observations, with every provenance field filled.

    IMPORTANT — double counting: this dataset carries one row per brand per manufacturer
    PLUS a roll-up row whose manufacturer is the 'Overall' label, repeating the same
    totals. Only the roll-up rows are emitted as observations; per-manufacturer rows are
    counted and reported as a warning. Summing both would double every figure.
    """
    if not records:
        return [], []
    columns = resolve_columns(list(records[0].keys()), dataset, data_year)
    retrieved_at = retrieved_at or dt.datetime.now(dt.timezone.utc)
    coverage = f"{dataset['coverage']} {COVERAGE_CAVEAT}"
    manufacturer_column = dataset["manufacturer_column"]
    total_label = str(dataset["manufacturer_total_label"]).strip().lower()

    observations: list[Observation] = []
    warnings: list[str] = []
    matched = [r for r in records if _matches(r, dataset, molecule, brand)]
    rollups = [r for r in matched
               if str(r.get(manufacturer_column) or "").strip().lower() == total_label]
    breakdown = len(matched) - len(rollups)
    if breakdown:
        warnings.append(
            f"{breakdown} per-manufacturer row(s) were not emitted: CMS repeats each brand's "
            f"totals under '{dataset['manufacturer_total_label']}' and again per manufacturer, "
            "so counting both would double the volume.")

    brands_seen = {str(r.get(dataset["brand_name_column"]) or "") for r in rollups}
    for record in rollups:
        record_brand = str(record.get(dataset["brand_name_column"]) or "") or None
        record_generic = str(record.get(dataset["generic_name_column"]) or "") or None
        # A generic-name query legitimately matches several brands, which must not be
        # summed as if they were one product. Flag rather than silently choosing.
        ambiguous = bool(molecule and not brand and len(brands_seen) > 1)
        for metric, column in columns.items():
            observations.append(Observation(
                source_kind=SourceKind.CMS_PART_D,
                geography=dataset["geography"],
                coverage=(coverage if metric is not SourceMetric.SPENDING
                          else f"{coverage} {dataset.get('spending_basis', '')}".strip()),
                period_label=str(data_year),
                period_start=dt.date(data_year, 1, 1),
                period_end=dt.date(data_year, 12, 31),
                metric=metric,
                unit=METRIC_UNITS.get(metric, "unknown"),
                value=parse_number(record.get(column)),
                currency="USD" if metric is SourceMetric.SPENDING else None,
                retrieved_at=retrieved_at,
                transformation=f"none — {column} as published by CMS ({retrieval_note})",
                source_url=source_url,
                source_identifier=source_identifier,
                molecule=record_generic or molecule,
                brand=record_brand or brand,
                ambiguous_match=ambiguous,
                provenance_class=provenance_class,
                retrieval_url=retrieval_url,
                archive_capture_date=archive_capture_date,
                content_sha256=content_sha256,
                file_verification=file_verification,
                raw_record={k: record.get(k) for k in
                            (dataset["brand_name_column"], dataset["generic_name_column"],
                             manufacturer_column, column)},
            ))
    return observations, warnings


class CmsPartDAdapter:
    """Live JSON API access to the CMS dataset."""

    source_kind = SourceKind.CMS_PART_D

    def __init__(self, client: httpx.Client | None = None, descriptor: dict | None = None):
        self._client = client
        self._descriptor = descriptor

    def _descriptor_or_load(self) -> dict:
        return self._descriptor if self._descriptor is not None else load_descriptor()

    def _get(self, url: str, params: dict) -> list[dict]:
        client = self._client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
        owns_client = self._client is None
        try:
            last_error: Exception | None = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = client.get(url, params=params)
                    if response.status_code == 429:
                        retry_after = response.headers.get("Retry-After")
                        delay = (float(retry_after) if (retry_after or "").isdigit()
                                 else BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
                        if attempt == MAX_ATTEMPTS:
                            raise httpx.HTTPError("CMS rate limit persisted across retries")
                        time.sleep(delay)
                        continue
                    response.raise_for_status()
                    payload = response.json()
                    return payload if isinstance(payload, list) else []
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if attempt == MAX_ATTEMPTS:
                        break
                    time.sleep(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
            raise httpx.HTTPError(str(last_error))
        finally:
            if owns_client:
                client.close()

    def search(self, *, molecule: str | None, brand: str | None, geography: str,
               period: str | None) -> SourceSearchResult:
        """Query the live CMS API. Never raises into the router."""
        try:
            dataset = validate_descriptor(self._descriptor_or_load())
        except (DescriptorError, OSError, json.JSONDecodeError) as exc:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE, unavailable_reason=str(exc))

        if geography != dataset["geography"]:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.NO_MATCHING_RECORDS,
                unavailable_reason=(
                    f"CMS Medicare Part D covers {dataset['geography']} only; {geography} is "
                    "outside its scope. Use a validated import or manual entry for this market."))
        if not (molecule or brand):
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.NO_MATCHING_RECORDS,
                unavailable_reason="Provide a molecule or brand name to search CMS Part D.")

        data_year = int(period) if period else int(dataset["latest_data_year"])
        if data_year not in dataset["available_data_years"]:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE,
                unavailable_reason=(
                    f"Data year {data_year} is not in this dataset; it carries "
                    f"{dataset['available_data_years']}."))

        try:
            records = self._get(dataset["api_url"], {"size": MAX_ROWS})
        except httpx.HTTPError as exc:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.API_UNAVAILABLE,
                unavailable_reason=(
                    f"CMS API did not answer ({exc}). The dataset is configured and verified; "
                    f"the bulk CSV at {dataset['csv_url']} can be ingested instead."))

        try:
            observations, warnings = records_to_observations(
                records, dataset, data_year, molecule=molecule, brand=brand,
                source_url=dataset["api_url"],
                source_identifier=str(dataset.get("api_dataset_uuid") or ""),
                retrieval_note="CMS data API")
        except ColumnResolutionError as exc:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE, unavailable_reason=str(exc))

        if not observations:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.NO_MATCHING_RECORDS, warnings=warnings,
                unavailable_reason=(
                    f"CMS Part D {data_year} has no rows matching "
                    f"{brand or molecule!r}. The source answered; it simply has no such drug."))
        return SourceSearchResult(
            source_kind=self.source_kind, available=True, status=SourceStatus.AVAILABLE,
            observations=observations, warnings=warnings,
            truncated=len(records) >= MAX_ROWS)


class CmsPartDFileIngestor:
    """Ingests the official CMS bulk CSV download.

    This is the supported route while data.cms.gov blocks automated API access. The file
    is the publisher's own artifact, so provenance is recorded as the CMS URL it is
    published at, with a note of how this copy was obtained.
    """

    source_kind = SourceKind.CMS_PART_D

    def __init__(self, descriptor: dict | None = None):
        self._descriptor = descriptor

    def _descriptor_or_load(self) -> dict:
        return self._descriptor if self._descriptor is not None else load_descriptor()

    @staticmethod
    def decode(payload: bytes) -> str:
        """CMS serves this file gzip-encoded; accept either form."""
        if len(payload) > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds {MAX_FILE_BYTES} bytes")
        if payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
            if len(payload) > MAX_FILE_BYTES:
                raise ValueError(f"decompressed file exceeds {MAX_FILE_BYTES} bytes")
        return payload.decode("utf-8-sig", errors="replace")

    def ingest(self, text: str, *, molecule: str | None = None, brand: str | None = None,
               data_year: int | None = None, retrieval_note: str = "official CMS CSV download",
               retrieved_at: dt.datetime | None = None, retrieval_url: str | None = None,
               archive_capture_date: dt.datetime | None = None) -> SourceSearchResult:
        """Parse an official CMS CSV and emit matching observations.

        `retrieval_url` is where these bytes were actually fetched from, when that is not
        the CMS publication URL — an Internet Archive capture, say. Supplying it marks
        every resulting observation an ARCHIVED CMS PUBLICATION rather than live CMS
        access, and records the archive URL and capture date alongside the CMS URL.

        The checksum is computed here from the bytes ingested, never taken on trust, and
        compared against the digest of the copy this integration was verified against.
        """
        try:
            dataset = validate_descriptor(self._descriptor_or_load())
        except (DescriptorError, OSError, json.JSONDecodeError) as exc:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE, unavailable_reason=str(exc))

        year = int(data_year) if data_year else int(dataset["latest_data_year"])
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        verification = classify_file(digest, dataset)
        provenance = (ProvenanceClass.ARCHIVED_CMS_PUBLICATION if retrieval_url
                      else ProvenanceClass.USER_SUPPLIED_FILE)
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE,
                unavailable_reason="The CMS file has no header row.")
        records = list(reader)

        try:
            observations, warnings = records_to_observations(
                records, dataset, year, molecule=molecule, brand=brand,
                source_url=dataset["csv_url"],
                source_identifier=str(dataset.get("csv_dataset_uuid") or ""),
                retrieval_note=retrieval_note, retrieved_at=retrieved_at,
                provenance_class=provenance, retrieval_url=retrieval_url,
                archive_capture_date=archive_capture_date, content_sha256=digest,
                file_verification=verification)
        except ColumnResolutionError as exc:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.CONFIGURATION_INCOMPLETE, unavailable_reason=str(exc))

        if not observations:
            return SourceSearchResult(
                source_kind=self.source_kind, available=False,
                status=SourceStatus.NO_MATCHING_RECORDS, warnings=warnings,
                unavailable_reason=(
                    f"The CMS {year} file has no rows matching {brand or molecule!r} "
                    f"({len(records)} rows read)."))
        if provenance is ProvenanceClass.ARCHIVED_CMS_PUBLICATION:
            warnings.append(
                f"Archived CMS publication: these bytes were retrieved from {retrieval_url} "
                f"(captured {archive_capture_date.isoformat() if archive_capture_date else 'date not stated'}), "
                f"not by live access to {dataset['csv_url']}. CMS remains the publisher.")
        if verification is FileVerificationStatus.VERIFIED:
            warnings.append(
                f"File verification: sha256 {digest[:16]}… matches the copy this integration "
                "was verified against.")
        else:
            warnings.append(
                f"File verification: sha256 {digest[:16]}… is not the copy this integration was "
                "verified against ({0}). Columns still resolved from its own header.".format(
                    verification.value))
        return SourceSearchResult(
            source_kind=self.source_kind, available=True, status=SourceStatus.AVAILABLE,
            observations=observations, warnings=warnings)


# --- Three independent health facts ------------------------------------------
#
# These are deliberately separate. A deployment can hold a verified file of the current
# reporting year and still have no API connectivity; it can have connectivity and an
# unrecognised file; it can have a verified file that CMS has since superseded. None of
# the three implies either of the others, so none of them is collapsed into one flag.

#: Akamai stamps its denials with a reference of this shape; CMS support needs it verbatim.
AKAMAI_REFERENCE_PATTERN = re.compile(r"Reference\s*#?\s*([0-9a-f.]+)", re.IGNORECASE)


def classify_file(digest: str, dataset: dict) -> FileVerificationStatus:
    """Does this file match the copy whose contents were verified?

    An unrecognised digest is not an error: CMS reissues these files, and the parser
    resolves columns from the file's own header either way. It is reported so nobody
    assumes a fresh upload carries the same bytes that were checked by hand.
    """
    expected = ((dataset.get("verified_file") or {}).get("content_sha256") or "").lower()
    if not expected:
        return FileVerificationStatus.UNRECOGNISED
    return (FileVerificationStatus.VERIFIED if digest.lower() == expected
            else FileVerificationStatus.UNRECOGNISED)


def classify_freshness(data_year: int, dataset: dict) -> PublicationFreshness:
    """Is the reporting year the newest CMS is known to have published?"""
    latest = dataset.get("latest_data_year")
    if latest is None:
        return PublicationFreshness.UNKNOWN
    if int(data_year) >= int(latest):
        return PublicationFreshness.CURRENT
    return PublicationFreshness.SUPERSEDED


@dataclass(frozen=True)
class ConnectivityReport:
    """One live probe of the CMS API, with everything CMS support would ask for."""

    status: ApiConnectivity
    endpoint: str
    checked_at: dt.datetime
    http_status: int | None = None
    akamai_reference: str | None = None
    detail: str | None = None

    def support_summary(self) -> str:
        """A paste-ready line for a CMS support ticket."""
        parts = [
            f"Endpoint: {self.endpoint}",
            f"UTC timestamp: {self.checked_at.isoformat()}",
            f"HTTP status: {self.http_status if self.http_status is not None else 'no response'}",
        ]
        if self.akamai_reference:
            parts.append(f"Akamai reference: {self.akamai_reference}")
        parts.append("No API key is published for this dataset, so this is not an auth failure.")
        return " | ".join(parts)


def probe_api(client: httpx.Client | None = None, descriptor: dict | None = None
              ) -> ConnectivityReport:
    """Check live CMS API reachability. Called on demand only — never during a forecast read.

    A 403 from the edge is reported as BLOCKED rather than an error, and its Akamai
    reference number is extracted so it can be quoted to CMS support verbatim.
    """
    checked_at = dt.datetime.now(dt.timezone.utc)
    try:
        dataset = validate_descriptor(descriptor or load_descriptor())
    except (DescriptorError, OSError, json.JSONDecodeError) as exc:
        return ConnectivityReport(
            status=ApiConnectivity.NOT_CHECKED, endpoint="(descriptor unusable)",
            checked_at=checked_at, detail=str(exc))

    endpoint = dataset["api_url"]
    owns_client = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = client.get(endpoint, params={"size": 1})
        # The edge HTML-escapes its denial page ("Reference&#32;&#35;18&#46;..."), so the
        # reference number only matches after unescaping.
        body = html.unescape(response.text[:4000])
        reference = None
        match = AKAMAI_REFERENCE_PATTERN.search(body)
        if match:
            reference = match.group(1)
        if response.status_code == 200:
            return ConnectivityReport(
                status=ApiConnectivity.REACHABLE, endpoint=endpoint, checked_at=checked_at,
                http_status=200)
        if response.status_code in (401, 403):
            return ConnectivityReport(
                status=ApiConnectivity.BLOCKED, endpoint=endpoint, checked_at=checked_at,
                http_status=response.status_code, akamai_reference=reference,
                detail=("Denied at the edge before reaching the dataset. No API key is "
                        "published for this dataset, so this is not an authentication failure."))
        return ConnectivityReport(
            status=ApiConnectivity.ERROR, endpoint=endpoint, checked_at=checked_at,
            http_status=response.status_code, akamai_reference=reference,
            detail=f"Unexpected status {response.status_code}.")
    except httpx.HTTPError as exc:
        return ConnectivityReport(
            status=ApiConnectivity.ERROR, endpoint=endpoint, checked_at=checked_at,
            detail=str(exc))
    finally:
        if owns_client:
            client.close()
