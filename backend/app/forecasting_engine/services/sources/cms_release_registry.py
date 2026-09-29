"""Release validation and promotion for CMS dataset files.

The distinction this module exists to enforce:

    A CHECKSUM IDENTIFIES A FILE. IT DOES NOT VERIFY THE SOURCE.

Matching a recorded digest means "these are the same bytes someone already examined". It
says nothing about whether the file is genuine, well-formed, or safe to forecast from.
Source verification is the separate, documented set of checks below — provenance, schema,
units and duplicate structure — which a new legitimate CMS release passes on its own
merits. Promoting a release is therefore a workflow, not an edit to a hardcoded digest.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass, field
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.forecasting_engine.core.units import ProvenanceClass, SourceKind, SourceMetric
from app.forecasting_engine.models.db_models import CmsDatasetRelease
from app.forecasting_engine.services.sources import cms_part_d

#: Validation statuses a release can hold.
PENDING = "pending"
VALIDATED = "validated"
REJECTED = "rejected"
SUPERSEDED = "superseded"

#: Units each metric must carry. A release whose units disagree is rejected rather than
#: quietly reinterpreted.
EXPECTED_UNITS = {
    SourceMetric.DOSAGE_UNITS: "dosage_units",
    SourceMetric.CLAIMS: "claims",
    SourceMetric.BENEFICIARIES: "beneficiaries",
    SourceMetric.SPENDING: "currency",
}


@dataclass
class CheckOutcome:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    """The documented outcome of validating one candidate release."""

    checks: list[CheckOutcome] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(CheckOutcome(name=name, passed=passed, detail=detail))

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail}
                       for c in self.checks],
        }

    def failures(self) -> list[str]:
        return [f"{c.name}: {c.detail}" for c in self.checks if not c.passed]


def validate_release(text: str, dataset: dict, data_year: int, *,
                     provenance_class: ProvenanceClass,
                     retrieval_url: str | None = None) -> tuple[ValidationReport, dict]:
    """Run every source-verification check against a candidate file.

    Returns the report plus the facts worth recording (digest, row count, resolved
    columns). Deliberately independent of whether the digest is already known: a new
    release is validated on its own merits.
    """
    report = ValidationReport()
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # 1. Provenance — the publication URL must be the publisher's, on an allowlisted host,
    #    and an archived retrieval must say where it actually came from.
    publication_host = urlparse(dataset.get("csv_url", "")).hostname
    provenance_ok = publication_host in cms_part_d.ALLOWED_HOSTS
    detail = f"publication host {publication_host!r}"
    if provenance_class is ProvenanceClass.ARCHIVED_CMS_PUBLICATION and not retrieval_url:
        provenance_ok = False
        detail += "; archived provenance claimed without a retrieval URL"
    elif retrieval_url:
        detail += f"; retrieved from {urlparse(retrieval_url).hostname!r}"
    report.add("provenance", provenance_ok, detail)

    # 2. Schema — the columns for the claimed data year must resolve from the file itself.
    reader = csv.DictReader(io.StringIO(text))
    header = list(reader.fieldnames or [])
    resolved: dict = {}
    try:
        columns = cms_part_d.resolve_columns(header, dataset, data_year)
        resolved = {metric.value: column for metric, column in columns.items()}
        report.add("schema", True,
                   f"{len(resolved)} metric column(s) resolved for {data_year}: "
                   f"{sorted(resolved.values())}")
    except cms_part_d.ColumnResolutionError as exc:
        columns = {}
        report.add("schema", False, str(exc))

    rows = list(reader)

    # 3. Units — every resolved metric must map to the unit this engine expects.
    if columns:
        mismatched = [m.value for m in columns
                      if cms_part_d.METRIC_UNITS.get(m) != EXPECTED_UNITS.get(m)]
        report.add("units", not mismatched,
                   "all metric units as expected" if not mismatched
                   else f"unexpected units for {mismatched}")
    else:
        report.add("units", False, "skipped: no columns resolved")

    # 4. Duplicates — CMS repeats each brand under the 'Overall' label and again per
    #    manufacturer. The roll-up must be present, or de-duplication cannot be relied on.
    manufacturer_column = dataset.get("manufacturer_column")
    total_label = str(dataset.get("manufacturer_total_label", "")).strip().lower()
    if rows and manufacturer_column in header:
        rollups = sum(1 for r in rows
                      if str(r.get(manufacturer_column) or "").strip().lower() == total_label)
        report.add("duplicates", rollups > 0,
                   f"{rollups} '{dataset.get('manufacturer_total_label')}' roll-up row(s) of "
                   f"{len(rows)}; per-manufacturer duplicates are excluded on ingest"
                   if rollups else
                   f"no '{dataset.get('manufacturer_total_label')}' roll-up rows found, so "
                   "brand totals cannot be de-duplicated safely")
    else:
        report.add("duplicates", False,
                   f"manufacturer column {manufacturer_column!r} absent; cannot de-duplicate")

    facts = {
        "content_sha256": digest,
        "row_count": len(rows),
        "resolved_columns": resolved,
        "header": header[:8],
    }
    return report, facts


def record_release(db: Session, dataset: dict, data_year: int, text: str, *,
                   provenance_class: ProvenanceClass, retrieval_url: str | None = None,
                   archive_capture_date: dt.datetime | None = None,
                   validated_by: int | None = None,
                   promote: bool = True) -> CmsDatasetRelease:
    """Validate a candidate file and record it, promoting it only if every check passes.

    An already-known digest is returned as-is rather than re-validated, so repeated
    ingests of the same file are cheap and do not churn the registry. A file that fails
    validation is kept with status `rejected` and its report, so the failure is visible
    rather than silent.
    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = (db.query(CmsDatasetRelease)
                .filter(CmsDatasetRelease.source_kind == SourceKind.CMS_PART_D.value,
                        CmsDatasetRelease.data_year == data_year,
                        CmsDatasetRelease.content_sha256 == digest)
                .one_or_none())
    if existing is not None:
        return existing

    report, facts = validate_release(
        text, dataset, data_year, provenance_class=provenance_class,
        retrieval_url=retrieval_url)
    now = dt.datetime.now(dt.timezone.utc)

    published_on = None
    raw_published = dataset.get("published_on")
    if raw_published:
        try:
            published_on = dt.date.fromisoformat(str(raw_published))
        except ValueError:
            published_on = None

    release = CmsDatasetRelease(
        source_kind=SourceKind.CMS_PART_D.value,
        dataset_uuid=str(dataset.get("csv_dataset_uuid") or ""),
        publication_url=dataset.get("csv_url", ""),
        release_label=dataset.get("csv_filename"),
        data_year=data_year,
        published_on=published_on,
        content_sha256=digest,
        row_count=facts["row_count"],
        resolved_columns=facts["resolved_columns"],
        provenance_class=provenance_class.value,
        retrieval_url=retrieval_url,
        archive_capture_date=archive_capture_date,
        validation_status=VALIDATED if report.passed else REJECTED,
        validation_report=report.as_dict(),
        is_active=False,
        first_seen_at=now,
        validated_at=now if report.passed else None,
        validated_by=validated_by if report.passed else None,
    )
    db.add(release)
    db.flush()

    if report.passed and promote:
        promote_release(db, release)
    db.commit()
    db.refresh(release)
    return release


def promote_release(db: Session, release: CmsDatasetRelease) -> None:
    """Make a validated release the active one, preserving what it replaces.

    The previous active release is marked `superseded` rather than deleted or rewritten,
    so every earlier forecast can still be traced to the file it was built on. A release
    that did not pass validation is never promoted.
    """
    if release.validation_status != VALIDATED:
        raise ValueError("only a validated release may be promoted")
    previous = (db.query(CmsDatasetRelease)
                .filter(CmsDatasetRelease.source_kind == release.source_kind,
                        CmsDatasetRelease.is_active.is_(True),
                        CmsDatasetRelease.id != release.id)
                .all())
    for row in previous:
        # An older reporting year is superseded; a same-year reissue is too.
        row.is_active = False
        if row.validation_status == VALIDATED:
            row.validation_status = SUPERSEDED
    release.is_active = True
    db.flush()


def active_release(db: Session) -> CmsDatasetRelease | None:
    return (db.query(CmsDatasetRelease)
            .filter(CmsDatasetRelease.source_kind == SourceKind.CMS_PART_D.value,
                    CmsDatasetRelease.is_active.is_(True))
            .one_or_none())
