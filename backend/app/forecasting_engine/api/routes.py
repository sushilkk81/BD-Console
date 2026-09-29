"""HTTP surface for forecasting.

Mounted without an /api prefix, like every other router in this app: the Next.js
catch-all proxy at frontend/app/api/[...path]/route.ts strips a leading /api before
forwarding, so these endpoints are reached from the browser at /api/forecast/...

No upstream fetch happens on a forecast GET. Only /sources/search and /sources/import
touch the source layer, and neither of them modifies an approved parameter set.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.forecasting_engine.api import schemas
from app.forecasting_engine.services import forecast_service
from app.forecasting_engine.services.source_cache import SOURCE_SEARCH_CACHE
from app.forecasting_engine.services.sources import tabular_import
from app.forecasting_engine.services.sources.base import SourceStatus
from app.forecasting_engine.services.sources import (cms_metadata_check, cms_part_d,
                                                      cms_release_registry)
from app.forecasting_engine.services.sources.cms_part_d import (CmsPartDAdapter,
                                                                 CmsPartDFileIngestor)
from app.models import User

logger = logging.getLogger("forecasting.routes")

router = APIRouter(prefix="/forecast", tags=["Forecasting"])

MAX_QUERY_LEN = 200


def get_cms_adapter() -> CmsPartDAdapter:
    """Dependency so tests can substitute a fake and never touch the network."""
    return CmsPartDAdapter()


def get_cms_file_ingestor() -> CmsPartDFileIngestor:
    """File ingestion touches no network at all — the caller supplies the CMS file."""
    return CmsPartDFileIngestor()


def _bounded(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    if len(trimmed) > MAX_QUERY_LEN:
        raise HTTPException(422, f"{field} must be at most {MAX_QUERY_LEN} characters")
    return trimmed or None


# --- Static routes are registered before the dynamic /{request_id} route below. ---

@router.get("/sources/search", response_model=schemas.SourceSearchOut)
def search_sources(
    request_id: int = Query(..., description="Request whose access rights govern this search"),
    molecule: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    geography: str = Query(...),
    period: str | None = Query(default=None),
    indication: str | None = Query(default=None),
    strength: str | None = Query(default=None),
    dosage_form: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    adapter: CmsPartDAdapter = Depends(get_cms_adapter),
):
    """Search public utilization evidence. Read-only: approved parameters are untouched."""
    # Authorize BEFORE consulting the cache, so a cached entry can never be served to
    # someone who may not see this request.
    forecast_service.authorize_request(db, request_id, current_user)

    molecule = _bounded(molecule, "molecule")
    brand = _bounded(brand, "brand")
    geography = _bounded(geography, "geography")
    period = _bounded(period, "period")
    if not (molecule or brand):
        raise HTTPException(422, "Provide a molecule or a brand to search for")

    cache_key = ("cms_part_d", molecule, brand, geography, period)
    result = SOURCE_SEARCH_CACHE.get(cache_key)
    if result is None:
        result = adapter.search(molecule=molecule, brand=brand, geography=geography, period=period)
        SOURCE_SEARCH_CACHE.set(cache_key, result)

    return schemas.SourceSearchOut(
        query_echo={"molecule": molecule, "brand": brand, "geography": geography,
                    "period": period, "indication": _bounded(indication, "indication"),
                    "strength": _bounded(strength, "strength"),
                    "dosage_form": _bounded(dosage_form, "dosage_form")},
        results=[forecast_service.in_flight_observation_to_out(o) for o in result.observations],
        available=result.available,
        status=result.status,
        unavailable_reason=result.unavailable_reason,
        truncated=result.truncated,
        warnings=result.warnings,
    )


@router.post("/sources/import", response_model=schemas.SourceSearchOut)
def import_sources(
    payload: schemas.SourceImportIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import user-owned CSV/JSON evidence. Stored beside the request, never merged into
    reviewed assumptions on its own."""
    forecast_service.authorize_request(db, payload.request_id, current_user)
    try:
        if payload.format == "csv":
            observations, errors = tabular_import.parse_csv(payload.payload or "")
        else:
            observations, errors = tabular_import.parse_rows(payload.rows or [])
    except tabular_import.ImportError_ as exc:
        raise HTTPException(422, str(exc))

    stored = forecast_service.persist_observations(
        db, payload.request_id, current_user.id, observations)
    result = tabular_import.import_result(observations, errors)
    return schemas.SourceSearchOut(
        query_echo={"request_id": payload.request_id, "format": payload.format},
        results=[forecast_service.observation_to_out(row) for row in stored],
        available=result.available,
        status=result.status,
        unavailable_reason=result.unavailable_reason,
        warnings=errors,
    )


@router.post("/sources/cms-part-d/ingest", response_model=schemas.SourceSearchOut)
def ingest_cms_part_d_file(
    payload: schemas.CmsFileIngestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    ingestor: CmsPartDFileIngestor = Depends(get_cms_file_ingestor),
):
    """Ingest the official CMS Part D bulk CSV.

    The supported route while data.cms.gov blocks automated API access. Columns are
    resolved from the file's own header, so a CMS rename fails loudly rather than
    producing wrong numbers. Stored beside the request like any other evidence — it does
    not alter a reviewed assumption.
    """
    forecast_service.authorize_request(db, payload.request_id, current_user)
    result = ingestor.ingest(
        payload.payload, molecule=payload.molecule, brand=payload.brand,
        data_year=payload.data_year, retrieval_note=payload.retrieval_note,
        retrieval_url=payload.retrieval_url,
        archive_capture_date=payload.archive_capture_date)

    # Every ingested file enters the release registry and is validated on its own merits
    # (provenance, schema, units, duplicates) — a new CMS release never needs a hardcoded
    # digest edit. Recording is best effort: a registry problem must not lose the data.
    if result.observations:
        try:
            dataset = cms_part_d.validate_descriptor(cms_part_d.load_descriptor())
            data_year = int(payload.data_year or dataset["latest_data_year"])
            release = cms_release_registry.record_release(
                db, dataset, data_year, payload.payload,
                provenance_class=result.observations[0].provenance_class,
                retrieval_url=payload.retrieval_url,
                archive_capture_date=payload.archive_capture_date,
                validated_by=current_user.id)
            checks = (release.validation_report or {}).get("checks", [])
            failed = [f"{c['name']} — {c['detail']}" for c in checks if not c["passed"]]
            if release.validation_status == cms_release_registry.REJECTED:
                result.warnings.append(
                    "Release validation failed, so this file was not promoted: "
                    + "; ".join(failed))
            elif release.is_active:
                result.warnings.append(
                    f"Release validated and promoted ({len(checks)} checks passed): "
                    f"reporting year {release.data_year}, sha256 "
                    f"{release.content_sha256[:16]}….")
        except Exception as exc:  # noqa: BLE001 - registry must never block ingestion
            logger.warning("CMS release registry could not record this file: %s", exc)

    stored = forecast_service.persist_observations(
        db, payload.request_id, current_user.id, result.observations)
    return schemas.SourceSearchOut(
        query_echo={"request_id": payload.request_id, "molecule": payload.molecule,
                    "brand": payload.brand, "data_year": payload.data_year,
                    "retrieval_note": payload.retrieval_note},
        results=[forecast_service.observation_to_out(row) for row in stored],
        available=result.available,
        status=result.status,
        unavailable_reason=result.unavailable_reason,
        warnings=result.warnings,
    )


def _freshness_label(reporting_year: int | None,
                     freshness: "cms_part_d.PublicationFreshness",
                     last_ok) -> str:
    """The sentence the UI shows. It names the reporting year and says plainly that this
    is not current-year observed sales, which is the easiest thing for a reader to assume
    and the most damaging to assume wrongly."""
    if reporting_year is None:
        return "No CMS reporting year loaded."
    latest = (last_ok.latest_data_year_seen if last_ok and last_ok.latest_data_year_seen
              else None)
    head = f"Latest published: {latest or reporting_year}"
    if freshness is cms_part_d.PublicationFreshness.SUPERSEDED:
        head = f"Latest published: {latest} — this forecast uses {reporting_year}"
    elif freshness is cms_part_d.PublicationFreshness.UNKNOWN:
        head = f"Reporting year {reporting_year} — latest published year not confirmed"
    return (f"{head}. These are observed {reporting_year} Medicare Part D figures, "
            "not current-year sales.")


@router.get("/sources/cms-part-d/status", response_model=schemas.CmsSourceStatusOut)
def cms_part_d_status(
    request_id: int = Query(..., description="Request whose access rights govern this check"),
    check_api: bool = Query(default=False,
                            description="Probe live CMS connectivity. Off by default: it is an "
                                        "outbound call and must never happen on a forecast read."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Report the three independent CMS source facts for this request.

    File verification, publication freshness and API connectivity are separate fields
    because they fail independently and are fixed differently.
    """
    forecast_service.authorize_request(db, request_id, current_user)
    dataset = cms_part_d.validate_descriptor(cms_part_d.load_descriptor())
    latest = forecast_service.latest_cms_observation(db, request_id)

    reporting_year = int(latest.period_label) if latest and latest.period_label.isdigit() else None
    last_ok = cms_metadata_check.latest_successful_check(db)
    last_any = cms_metadata_check.latest_check(db)
    freshness = cms_metadata_check.freshness_for(reporting_year, dataset, last_ok)
    release = cms_release_registry.active_release(db)

    connectivity = cms_part_d.ApiConnectivity.NOT_CHECKED
    report = None
    if check_api:
        report = cms_part_d.probe_api()
        connectivity = report.status

    return schemas.CmsSourceStatusOut(
        dataset_title=dataset.get("title", "Medicare Part D Spending by Drug"),
        publication_url=dataset["csv_url"],
        reporting_year=reporting_year,
        latest_published_year=int(dataset["latest_data_year"]),
        file_verification=(cms_part_d.FileVerificationStatus(latest.file_verification)
                           if latest and latest.file_verification else None),
        file_sha256=latest.content_sha256 if latest else None,
        publication_freshness=freshness,
        published_on=release.published_on if release else None,
        last_metadata_check_at=forecast_service.aware(last_any.checked_at) if last_any else None,
        last_metadata_check_status=last_any.status if last_any else None,
        metadata_check_detail=last_any.detail if last_any else None,
        new_release_detected=bool(last_any.new_release_detected) if last_any else False,
        freshness_label=_freshness_label(reporting_year, freshness, last_ok),
        active_release_status=release.validation_status if release else None,
        active_release_validated_at=(forecast_service.aware(release.validated_at)
                                     if release else None),
        active_release_checks=((release.validation_report or {}).get("checks")
                               if release else None),
        api_connectivity=connectivity,
        api_endpoint=dataset["api_url"],
        api_http_status=report.http_status if report else None,
        api_checked_at=report.checked_at if report else None,
        akamai_reference=report.akamai_reference if report else None,
        api_detail=report.detail if report else None,
        support_summary=report.support_summary() if report else None,
        last_successful_refresh=forecast_service.aware(latest.retrieved_at) if latest else None,
        last_refresh_provenance=(cms_part_d.ProvenanceClass(latest.provenance_class)
                                 if latest else None),
        retrieval_url=latest.retrieval_url if latest else None,
        archive_capture_date=forecast_service.aware(latest.archive_capture_date) if latest else None,
        observation_count=forecast_service.count_cms_observations(db, request_id),
    )


@router.post("/upsert", response_model=schemas.ForecastCollectionOut)
def upsert_forecast(
    payload: schemas.ForecastUpsertIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate, authorize and persist a complete parameter set, returning the forecast."""
    forecast_service.authorize_request(db, payload.request_id, current_user)
    collection = forecast_service.upsert_parameters(db, current_user, payload)
    # Supersede any cached source search for this request's configuration; forecasts
    # themselves are recomputed on every read, so there is nothing else to invalidate.
    SOURCE_SEARCH_CACHE.clear()
    return collection


@router.get("/{request_id}", response_model=schemas.ForecastCollectionOut)
def get_forecast(
    request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the saved forecast for a request. Never fetches upstream data."""
    forecast_service.authorize_request(db, request_id, current_user)
    return forecast_service.load_collection(db, request_id)
