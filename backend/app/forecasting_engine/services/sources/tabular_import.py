"""Validated CSV/JSON import and manual entry for markets no public source covers.

This is the path for user-owned licensed data. It asks for the same provenance a
connector records — geography, coverage, period, metric, unit, and where the number
came from — so an imported row is as auditable as a fetched one and is never mistaken
for something this application looked up itself.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from app.forecasting_engine.core.units import SourceKind, SourceMetric, is_valid_currency_code
from app.forecasting_engine.services.sources.base import (MAX_ROWS, Observation,
                                                           SourceSearchResult, SourceStatus)

#: Byte ceiling on an uploaded payload, checked before parsing.
MAX_PAYLOAD_BYTES = 1_000_000

REQUIRED_COLUMNS = ("geography", "coverage", "period_label", "metric", "unit", "value")
OPTIONAL_COLUMNS = ("molecule", "brand", "strength", "dosage_form", "currency",
                    "source_url", "source_identifier", "transformation")
ALLOWED_COLUMNS = frozenset(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)

#: Values that mean "the source did not report this", which stay NULL rather than 0.
NULL_TOKENS = frozenset({"", "*", "na", "n/a", "null", "none", "suppressed", "redacted"})


class ImportError_(ValueError):
    """The payload could not be parsed at all. Row-level problems are reported per row."""


def _parse_value(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in NULL_TOKENS:
        return None
    try:
        return Decimal(text.replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"value {raw!r} is not a number") from exc


def parse_rows(rows: list[dict]) -> tuple[list[Observation], list[str]]:
    """Validate already-parsed records into Observations, collecting per-row errors."""
    retrieved_at = dt.datetime.now(dt.timezone.utc)
    observations: list[Observation] = []
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        cleaned = {k.strip(): (v.strip() if isinstance(v, str) else v)
                   for k, v in row.items() if k is not None}
        unknown = set(cleaned) - ALLOWED_COLUMNS
        if unknown:
            errors.append(f"row {index}: unknown column(s) {sorted(unknown)}")
            continue
        missing = [c for c in REQUIRED_COLUMNS if not str(cleaned.get(c, "")).strip()
                   and c != "value"]
        if missing:
            errors.append(f"row {index}: missing required value(s) {missing}")
            continue
        if "value" not in cleaned:
            errors.append(f"row {index}: missing required column 'value' "
                          "(leave it blank for a suppressed figure)")
            continue
        try:
            metric = SourceMetric(str(cleaned["metric"]).strip().lower())
        except ValueError:
            errors.append(f"row {index}: metric {cleaned['metric']!r} is not one of "
                          f"{[m.value for m in SourceMetric]}")
            continue
        try:
            value = _parse_value(cleaned.get("value"))
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
            continue
        if value is not None and value < 0:
            errors.append(f"row {index}: value must not be negative")
            continue
        currency = (cleaned.get("currency") or "").strip().upper() or None
        if metric is SourceMetric.SPENDING and not currency:
            errors.append(f"row {index}: spending rows require a currency")
            continue
        if currency and not is_valid_currency_code(currency):
            errors.append(f"row {index}: currency {currency!r} is not a 3-letter ISO code")
            continue
        observations.append(Observation(
            source_kind=SourceKind.FILE_IMPORT,
            geography=str(cleaned["geography"]),
            coverage=str(cleaned["coverage"]),
            period_label=str(cleaned["period_label"]),
            metric=metric,
            unit=str(cleaned["unit"]),
            value=value,
            currency=currency,
            retrieved_at=retrieved_at,
            transformation=str(cleaned.get("transformation") or "none — as supplied by importer"),
            source_url=str(cleaned.get("source_url") or "") or None,
            source_identifier=str(cleaned.get("source_identifier") or "") or None,
            molecule=str(cleaned.get("molecule") or "") or None,
            brand=str(cleaned.get("brand") or "") or None,
            strength=str(cleaned.get("strength") or "") or None,
            dosage_form=str(cleaned.get("dosage_form") or "") or None,
            raw_record=dict(cleaned),
        ))
    return observations, errors


def parse_csv(payload: str) -> tuple[list[Observation], list[str]]:
    """Parse a CSV upload. Bounded by MAX_PAYLOAD_BYTES and MAX_ROWS."""
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ImportError_(f"CSV payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    reader = csv.DictReader(io.StringIO(payload))
    if reader.fieldnames is None:
        raise ImportError_("CSV payload has no header row")
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            return _with_truncation(rows)
        rows.append(row)
    return parse_rows(rows)


def _with_truncation(rows: list[dict]) -> tuple[list[Observation], list[str]]:
    observations, errors = parse_rows(rows)
    errors.append(f"import truncated at {MAX_ROWS} rows; split the file and import again")
    return observations, errors


def import_result(observations: list[Observation], errors: list[str]) -> SourceSearchResult:
    """Wrap parsed rows in the same result shape a connector returns."""
    if not observations and errors:
        return SourceSearchResult(
            source_kind=SourceKind.FILE_IMPORT, available=False,
            status=SourceStatus.NO_MATCHING_RECORDS,
            unavailable_reason="No valid rows in the import.", warnings=errors)
    return SourceSearchResult(
        source_kind=SourceKind.FILE_IMPORT, available=True,
        status=SourceStatus.AVAILABLE, observations=observations, warnings=errors)
