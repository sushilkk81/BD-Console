"""Recurring check for new CMS releases.

Run it the way this app runs its other operational tasks — as a command, from whatever
scheduler the deployment has (a Render cron service, host cron, or CI). There is no
scheduler runtime in this application and this does not add one:

    python -m app.forecasting_engine.services.sources.cms_metadata_check

It reads CMS's own published metadata (via the HHS catalogue record, which is reachable
where data.cms.gov's API is not), records one row per run, and reports whether a newer
reporting year or a reissue of the current file has appeared. It never promotes anything
by itself: a detected release still goes through the validation workflow in
cms_release_registry.py.

Freshness depends on these rows. If the newest successful check is older than
STALE_AFTER_DAYS, or none has ever succeeded, freshness is reported unknown or stale
instead of continuing to claim the data is current.
"""
from __future__ import annotations

import datetime as dt
import logging

import httpx
from sqlalchemy.orm import Session

from app.forecasting_engine.core.units import PublicationFreshness, SourceKind
from app.forecasting_engine.models.db_models import CmsMetadataCheck
from app.forecasting_engine.services.sources import cms_part_d
from app.forecasting_engine.services.sources.base import HTTP_TIMEOUT_SECONDS

logger = logging.getLogger("forecasting.cms_metadata_check")

#: Expected cadence. CMS publishes this dataset annually, so a monthly check is ample;
#: the grace period is what turns "we have not looked in a while" into a visible state.
CHECK_INTERVAL_DAYS = 30
STALE_AFTER_DAYS = 45

OK = "ok"
UNREACHABLE = "unreachable"
ERROR = "error"


def _parse_temporal_end_year(metadata: dict) -> tuple[int | None, dt.date | None]:
    """Pull the latest reporting year and publication date out of the catalogue record."""
    custom = ((metadata.get("metadata") or {}).get("custom_fields") or {})
    common = custom.get("Common Core") or {}
    year = None
    temporal = common.get("Temporal Applicability")
    if temporal and "/" in str(temporal):
        end = str(temporal).split("/")[-1]
        try:
            year = dt.date.fromisoformat(end).year
        except ValueError:
            year = None
    published = None
    stamp = metadata.get("rowsUpdatedAt")
    if stamp:
        try:
            published = dt.datetime.fromtimestamp(int(stamp), dt.timezone.utc).date()
        except (TypeError, ValueError, OSError):
            published = None
    return year, published


def run_check(db: Session, client: httpx.Client | None = None,
              descriptor: dict | None = None) -> CmsMetadataCheck:
    """Perform one metadata check and record the result. Never raises into a caller."""
    checked_at = dt.datetime.now(dt.timezone.utc)
    dataset = cms_part_d.validate_descriptor(descriptor or cms_part_d.load_descriptor())
    metadata_url = dataset.get("metadata_url")

    row = CmsMetadataCheck(
        source_kind=SourceKind.CMS_PART_D.value, checked_at=checked_at,
        status=ERROR, metadata_url=metadata_url)

    if not metadata_url:
        row.status = ERROR
        row.detail = "No metadata_url configured for this dataset."
        db.add(row)
        db.commit()
        return row

    owns_client = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = client.get(metadata_url)
        if response.status_code != 200:
            row.status = UNREACHABLE
            row.detail = (f"Metadata endpoint returned HTTP {response.status_code}. "
                          "Freshness is reported as stale rather than assumed current.")
        else:
            metadata = response.json()
            year, published = _parse_temporal_end_year(metadata)
            row.status = OK
            row.latest_data_year_seen = year
            row.published_on_seen = published
            row.latest_release_label = metadata.get("name")
            row.raw_metadata = {
                "name": metadata.get("name"),
                "rowsUpdatedAt": metadata.get("rowsUpdatedAt"),
                "custom_fields": ((metadata.get("metadata") or {}).get("custom_fields") or {}),
            }
            configured = int(dataset["latest_data_year"])
            if year and year > configured:
                row.new_release_detected = True
                row.detail = (
                    f"CMS now publishes reporting year {year}; this deployment is configured "
                    f"for {configured}. Download the new file and ingest it — it enters the "
                    "validation workflow before it can be promoted.")
            else:
                row.detail = (f"No newer reporting year. CMS latest is {year or 'unstated'}; "
                              f"configured {configured}.")
    except (httpx.HTTPError, ValueError) as exc:
        row.status = UNREACHABLE
        row.detail = (f"Could not reach or parse CMS metadata ({exc}). Freshness is reported "
                      "as stale rather than assumed current.")
    finally:
        if owns_client:
            client.close()

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def latest_check(db: Session) -> CmsMetadataCheck | None:
    return (db.query(CmsMetadataCheck)
            .filter(CmsMetadataCheck.source_kind == SourceKind.CMS_PART_D.value)
            .order_by(CmsMetadataCheck.checked_at.desc(), CmsMetadataCheck.id.desc())
            .first())


def latest_successful_check(db: Session) -> CmsMetadataCheck | None:
    return (db.query(CmsMetadataCheck)
            .filter(CmsMetadataCheck.source_kind == SourceKind.CMS_PART_D.value,
                    CmsMetadataCheck.status == OK)
            .order_by(CmsMetadataCheck.checked_at.desc(), CmsMetadataCheck.id.desc())
            .first())


def freshness_for(reporting_year: int | None, dataset: dict,
                  last_ok: CmsMetadataCheck | None,
                  now: dt.datetime | None = None) -> PublicationFreshness:
    """Freshness, accounting for whether we have actually looked recently.

    Never reports CURRENT on the strength of a configured constant alone: without a
    recent successful metadata check we cannot know CMS has not published a newer year,
    so the honest answer is UNKNOWN.
    """
    if reporting_year is None:
        return PublicationFreshness.UNKNOWN
    now = now or dt.datetime.now(dt.timezone.utc)
    if last_ok is None:
        return PublicationFreshness.UNKNOWN
    checked_at = last_ok.checked_at
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=dt.timezone.utc)
    if (now - checked_at).days > STALE_AFTER_DAYS:
        return PublicationFreshness.UNKNOWN
    latest_known = last_ok.latest_data_year_seen or int(dataset["latest_data_year"])
    return (PublicationFreshness.CURRENT if int(reporting_year) >= int(latest_known)
            else PublicationFreshness.SUPERSEDED)


def main() -> int:
    """Command entry point for the scheduler."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        row = run_check(db)
        logger.info("CMS metadata check: status=%s latest_year=%s new_release=%s detail=%s",
                    row.status, row.latest_data_year_seen, row.new_release_detected, row.detail)
        return 0 if row.status == OK else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
