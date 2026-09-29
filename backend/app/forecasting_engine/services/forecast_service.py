"""Orchestration: authorize -> load -> calculate -> persist.

Holds no mathematics of its own (that is core/math_engine.py) and makes no outbound
call (that is services/sources/). Source ingestion never writes into a reviewed
parameter set: observations are stored beside the parameters, and a person decides
whether to adopt one.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.forecasting_engine.api import schemas
from app.forecasting_engine.core import math_engine as me
from app.forecasting_engine.core.units import (PRICE_BASIS_METRIC, ForecastMode, PriceBasis,
                                                ProvenanceClass, SourceKind, SourceMetric,
                                                VolumeMetric)
from app.forecasting_engine.models.db_models import (MoleculeForecastAudit,
                                                      MoleculeForecastParameter,
                                                      MoleculeSourceObservation)
from app.forecasting_engine.services.sources.base import Observation
from app.models import Request, SkuRow, User
# Reused rather than reimplemented: forecasts must be visible to exactly the same
# people as the request they belong to, and a second copy of this rule would drift.
from app.routers.requests import _visible_or_404

#: An observation older than this is surfaced as stale in the UI. Utilization datasets
#: publish roughly annually, so half a year is late enough to warrant a second look
#: without flagging every recent figure.
SOURCE_STALE_AFTER_DAYS = 180

#: Tokens that suggest a combination product, for which whole-product mass is not a
#: meaningful figure without per-ingredient strengths.
_COMBINATION_TOKENS = ("+", "/", " and ")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime | None) -> dt.datetime | None:
    """SQLite drops tzinfo on round-trip; treat a naive stored value as UTC."""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


def authorize_request(db: Session, request_id: int, user: User) -> Request:
    """404 (not 403) for a request the user cannot see, matching the rest of the app."""
    req, _ = _visible_or_404(db, request_id, user)
    return req


def looks_like_combination(molecule: str | None) -> bool:
    return bool(molecule) and any(token in molecule.lower() for token in _COMBINATION_TOKENS)


def _conversions(row: MoleculeForecastParameter) -> me.ConversionAssumptions:
    return me.ConversionAssumptions(
        units_per_patient_per_year=row.units_per_patient_per_year,
        units_per_pack=row.units_per_pack,
        active_ingredient_mg_per_unit=row.active_ingredient_mg_per_unit,
        company_capture_share=row.company_capture_share,
    )


def _scenario(row: MoleculeForecastParameter, peak_share: float,
              calendar_years: list[int]) -> me.ScenarioTrajectory:
    conversions = _conversions(row)
    if row.forecast_mode == ForecastMode.EPIDEMIOLOGY.value:
        return me.epidemiology_scenario(
            target_population=float(row.target_population or 0),
            peak_share=peak_share,
            ramp_speed=row.ramp_speed,
            inflection_year=row.inflection_year,
            calendar_years=calendar_years,
            launch_year=row.launch_year,
            conversions=conversions,
        )
    return me.observed_volume_scenario(
        reference_units=float(row.reference_units or 0),
        reference_year=int(row.reference_year or row.forecast_start_year),
        annual_growth_rate=float(row.annual_growth_rate or 0.0),
        peak_capture_share=peak_share,
        ramp_speed=row.ramp_speed,
        inflection_year=row.inflection_year,
        calendar_years=calendar_years,
        launch_year=row.launch_year,
        conversions=conversions,
    )


def _priced_series(trajectory: me.ScenarioTrajectory, basis: PriceBasis) -> list[float] | None:
    metric = PRICE_BASIS_METRIC[basis]
    if metric is VolumeMetric.DOSAGE_UNITS:
        return trajectory.business_dosage_units
    if metric is VolumeMetric.PACKS:
        return trajectory.business_packs
    return trajectory.business_api_kg


def _collect_warnings(row: MoleculeForecastParameter, calendar_years: list[int],
                      trajectory: me.ScenarioTrajectory) -> list[str]:
    warnings: list[str] = []

    prelaunch = [y for y in calendar_years if y < row.launch_year]
    if prelaunch:
        warnings.append(
            f"{len(prelaunch)} prelaunch calendar year(s) ({prelaunch[0]}-{prelaunch[-1]}) are "
            f"zero: the forecast is conditional on launch in {row.launch_year}.")

    if row.ramp_speed > me.RAMP_SPEED_WARN_ABOVE:
        warnings.append(
            f"ramp_speed {row.ramp_speed} is above {me.RAMP_SPEED_WARN_ABOVE}; adoption is "
            "effectively a step change between adjacent years.")

    if row.forecast_mode == ForecastMode.EPIDEMIOLOGY.value:
        warnings.append(
            f"target_population is a {row.population_basis} population treated on a "
            f"{row.treatment_basis} basis; addressable patients are held flat across the "
            "window because no epidemiological growth assumption was supplied.")
        if row.units_per_patient_per_year is None:
            warnings.append(
                "No units_per_patient_per_year: dosage units, packs, API kg and revenue are "
                "unavailable. Patients are reported alone.")
        elif row.company_capture_share is None:
            warnings.append(
                "No company_capture_share: the product's total demand is shown, but our "
                "obtainable business volume is not modelled.")
    else:
        warnings.append(
            "Volumes inherit the coverage of the reference data. They have NOT been scaled "
            "to a national or global market; that needs an explicit coverage factor.")
        if row.reference_coverage_note:
            warnings.append(f"Reference coverage: {row.reference_coverage_note}")

    if trajectory.business_api_kg is not None:
        warnings.append(
            "API kg is contained active-ingredient demand, not a manufacturing input "
            "requirement: no yield, salt-factor or potency adjustment has been applied.")
    if looks_like_combination(row.molecule):
        if row.active_ingredient_mg_per_unit is None:
            warnings.append(
                f"{row.molecule} looks like a combination product and no per-ingredient "
                "active_ingredient_mg_per_unit was supplied, so mass conversion is refused "
                "rather than computed on whole-product strength.")
        else:
            warnings.append(
                f"{row.molecule} looks like a combination product: API kg is the mass of the "
                "single ingredient described by active_ingredient_mg_per_unit, not of the "
                "whole product.")

    if row.net_price is not None and row.price_basis is not None:
        if _priced_series(trajectory, PriceBasis(row.price_basis)) is None:
            warnings.append(
                f"Revenue is unavailable: no {PRICE_BASIS_METRIC[PriceBasis(row.price_basis)].value} "
                "series exists to price. Supply the missing conversion input.")
        warnings.append(
            "Revenue uses the supplied net selling price. Public gross spending is not "
            "manufacturer net revenue and is never substituted here.")
    return warnings


def _unit_metadata(row: MoleculeForecastParameter) -> schemas.UnitMetadata:
    return schemas.UnitMetadata(
        patients=("annual treated patients"
                  if row.forecast_mode == ForecastMode.EPIDEMIOLOGY.value else None),
        dosage_units="finished-product dosage units per year",
        packs="packs per year" if row.units_per_pack else None,
        api_kg=("kg contained active ingredient per year"
                if row.active_ingredient_mg_per_unit else None),
        revenue=(f"{row.price_currency} per year at {row.price_basis}"
                 if row.net_price is not None else None),
    )


def _assumption_summary(row: MoleculeForecastParameter) -> dict:
    """Every input that moved a number, so the output can be re-derived by hand."""
    summary = {
        "forecast_mode": row.forecast_mode,
        "molecule": row.molecule,
        "brand": row.brand,
        "geography": row.geography,
        "indication": row.indication,
        "strength": row.strength,
        "dosage_form": row.dosage_form,
        "forecast_start_year": row.forecast_start_year,
        "launch_year": row.launch_year,
        "base_peak_share": row.base_peak_share,
        "upside_peak_share": row.upside_peak_share,
        "ramp_speed": row.ramp_speed,
        "inflection_year": row.inflection_year,
        "adoption_formula": "expit(ramp_speed * (t - inflection_year)), t = years since launch",
        "peak_share_is_asymptotic": True,
        "units_per_patient_per_year": row.units_per_patient_per_year,
        "units_per_patient_basis": row.units_per_patient_basis,
        "units_per_pack": row.units_per_pack,
        "active_ingredient_mg_per_unit": row.active_ingredient_mg_per_unit,
        "company_capture_share": row.company_capture_share,
        "probability_of_success": row.probability_of_success,
        "net_price": str(row.net_price) if row.net_price is not None else None,
        "price_currency": row.price_currency,
        "price_basis": row.price_basis,
        "override_reason": row.override_reason,
        "overridden_source_value": row.overridden_source_value,
    }
    if row.forecast_mode == ForecastMode.EPIDEMIOLOGY.value:
        summary.update({
            "target_population": row.target_population,
            "population_basis": row.population_basis,
            "treatment_basis": row.treatment_basis,
        })
    else:
        summary.update({
            "reference_units": row.reference_units,
            "reference_year": row.reference_year,
            "annual_growth_rate": row.annual_growth_rate,
            "reference_coverage_note": row.reference_coverage_note,
        })
    return summary


def observation_to_out(obs: MoleculeSourceObservation) -> schemas.ObservationOut:
    retrieved = _aware(obs.retrieved_at)
    stale = bool(retrieved and (_now() - retrieved).days > SOURCE_STALE_AFTER_DAYS)
    return schemas.ObservationOut(
        id=obs.id, source_kind=SourceKind(obs.source_kind), source_url=obs.source_url,
        source_identifier=obs.source_identifier, molecule=obs.molecule, brand=obs.brand,
        geography=obs.geography, coverage=obs.coverage, period_label=obs.period_label,
        metric=SourceMetric(obs.metric), unit=obs.unit,
        value=Decimal(str(obs.value)) if obs.value is not None else None,
        currency=obs.currency, strength=obs.strength, dosage_form=obs.dosage_form,
        transformation=obs.transformation, ambiguous_match=obs.ambiguous_match,
        retrieved_at=retrieved, stale=stale,
        provenance_class=ProvenanceClass(obs.provenance_class),
        retrieval_url=obs.retrieval_url, archive_capture_date=_aware(obs.archive_capture_date),
        content_sha256=obs.content_sha256,
    )


def in_flight_observation_to_out(obs: Observation) -> schemas.ObservationOut:
    return schemas.ObservationOut(
        id=None, source_kind=obs.source_kind, source_url=obs.source_url,
        source_identifier=obs.source_identifier, molecule=obs.molecule, brand=obs.brand,
        geography=obs.geography, coverage=obs.coverage, period_label=obs.period_label,
        metric=obs.metric, unit=obs.unit, value=obs.value, currency=obs.currency,
        strength=obs.strength, dosage_form=obs.dosage_form, transformation=obs.transformation,
        ambiguous_match=obs.ambiguous_match, retrieved_at=obs.retrieved_at, stale=False,
        provenance_class=obs.provenance_class, retrieval_url=obs.retrieval_url,
        archive_capture_date=obs.archive_capture_date, content_sha256=obs.content_sha256,
    )


def compute_forecast(db: Session, row: MoleculeForecastParameter) -> schemas.ForecastOut:
    """Calculate both scenarios for one stored parameter set. No I/O beyond reading
    the observation this parameter set cites."""
    calendar_years = me.forecast_calendar_years(row.forecast_start_year)
    base = _scenario(row, row.base_peak_share, calendar_years)
    upside = _scenario(row, row.upside_peak_share, calendar_years)

    scenarios: dict[str, schemas.ScenarioOut] = {}
    for name, trajectory in (("base", base), ("upside", upside)):
        revenue = None
        if row.net_price is not None and row.price_basis is not None:
            priced = _priced_series(trajectory, PriceBasis(row.price_basis))
            revenue = me.scenario_revenue(trajectory, Decimal(str(row.net_price)), priced)
        risk_adjusted = None
        if row.probability_of_success is not None:
            risk_adjusted = me.apply_probability_of_success(
                trajectory.business_dosage_units, row.probability_of_success)
        scenarios[name] = schemas.ScenarioOut(
            addressable_patients=trajectory.addressable_patients,
            patients=trajectory.patients,
            addressable_dosage_units=trajectory.addressable_dosage_units,
            business_dosage_units=trajectory.business_dosage_units,
            business_packs=trajectory.business_packs,
            business_api_kg=trajectory.business_api_kg,
            business_revenue=revenue,
            risk_adjusted_business_dosage_units=risk_adjusted,
        )

    references = []
    if row.source_observation_id is not None:
        obs = db.get(MoleculeSourceObservation, row.source_observation_id)
        if obs is not None:
            references.append(observation_to_out(obs))

    warnings = _collect_warnings(row, calendar_years, base)
    if row.override_reason:
        warnings.append(
            f"A reviewed value overrides the source figure "
            f"{row.overridden_source_value!r}: {row.override_reason}")
    if any(ref.stale for ref in references):
        warnings.append(
            f"Cited source evidence is older than {SOURCE_STALE_AFTER_DAYS} days; "
            "re-check the source before relying on this forecast.")

    return schemas.ForecastOut(
        deal_id=row.request_id, request_id=row.request_id, sku_row_id=row.sku_row_id,
        revision=row.revision, model_version=row.model_version,
        forecast_mode=ForecastMode(row.forecast_mode), calendar_years=calendar_years,
        base_case=scenarios["base"], upside_case=scenarios["upside"],
        unit_metadata=_unit_metadata(row), assumption_summary=_assumption_summary(row),
        source_references=references, updated_at=_aware(row.updated_at), warnings=warnings,
    )


def _parameter_rows(db: Session, request_id: int) -> list[MoleculeForecastParameter]:
    return (db.query(MoleculeForecastParameter)
            .filter(MoleculeForecastParameter.request_id == request_id)
            .order_by(MoleculeForecastParameter.sku_row_id.is_(None).desc(),
                      MoleculeForecastParameter.sku_row_id,
                      MoleculeForecastParameter.id)
            .all())


def load_collection(db: Session, request_id: int) -> schemas.ForecastCollectionOut:
    rows = _parameter_rows(db, request_id)
    if not rows:
        return schemas.ForecastCollectionOut(
            request_id=request_id, granularity="none", forecasts=[],
            warnings=["No forecast parameters saved for this request yet."])
    granularity = "request" if rows[0].sku_row_id is None else "sku"
    collection_warnings = []
    if granularity == "sku":
        collection_warnings.append(
            "Per-SKU forecasts. Summing them gives the request total; there is no separate "
            "request-level set, so nothing is double-counted.")
    return schemas.ForecastCollectionOut(
        request_id=request_id, granularity=granularity,
        forecasts=[compute_forecast(db, row) for row in rows],
        warnings=collection_warnings)


_ASSIGNABLE_FIELDS = (
    "molecule", "brand", "geography", "indication", "strength", "dosage_form",
    "forecast_start_year", "launch_year", "target_population", "population_basis",
    "treatment_basis", "reference_units", "reference_year", "annual_growth_rate",
    "reference_coverage_note", "base_peak_share", "upside_peak_share", "ramp_speed",
    "inflection_year", "units_per_patient_per_year", "units_per_patient_basis",
    "units_per_pack", "active_ingredient_mg_per_unit", "company_capture_share",
    "probability_of_success", "net_price", "price_currency", "source_observation_id",
    "override_reason", "overridden_source_value",
)


def _apply(row: MoleculeForecastParameter, params: schemas.ForecastParametersIn) -> None:
    for field in _ASSIGNABLE_FIELDS:
        value = getattr(params, field)
        setattr(row, field, value.value if hasattr(value, "value") else value)
    row.forecast_mode = params.forecast_mode.value
    row.price_basis = params.price_basis.value if params.price_basis else None
    row.model_version = me.MODEL_VERSION


def _validate_granularity(db: Session, request_id: int, sku_row_id: int | None) -> None:
    """A request is forecast at one level only, so the rows can be summed safely."""
    if sku_row_id is not None:
        sku = db.get(SkuRow, sku_row_id)
        if sku is None or sku.request_id != request_id:
            raise HTTPException(422, "sku_row_id does not belong to this request")
    existing = _parameter_rows(db, request_id)
    if not existing:
        return
    existing_is_request_level = existing[0].sku_row_id is None
    if sku_row_id is None and not existing_is_request_level:
        raise HTTPException(
            422, "This request already has per-SKU forecasts. Delete them before adding a "
                 "request-level forecast, or the same volume would be counted twice.")
    if sku_row_id is not None and existing_is_request_level:
        raise HTTPException(
            422, "This request already has a request-level forecast. Remove it before adding "
                 "per-SKU forecasts, or the same volume would be counted twice.")


def _validate_source_observation(db: Session, request_id: int, observation_id: int | None) -> None:
    if observation_id is None:
        return
    obs = db.get(MoleculeSourceObservation, observation_id)
    if obs is None or (obs.request_id is not None and obs.request_id != request_id):
        raise HTTPException(422, "source_observation_id does not belong to this request")


def upsert_parameters(db: Session, user: User, payload: schemas.ForecastUpsertIn
                      ) -> schemas.ForecastCollectionOut:
    """Persist a complete parameter set atomically, with revision-based concurrency.

    A client that saved against revision N must send N. If the stored revision has moved
    on, the write is refused with 409 and the caller re-reads — an edit is never lost by
    being silently overwritten.
    """
    params = payload.parameters
    _validate_granularity(db, payload.request_id, params.sku_row_id)
    _validate_source_observation(db, payload.request_id, params.source_observation_id)

    query = (db.query(MoleculeForecastParameter)
             .filter(MoleculeForecastParameter.request_id == payload.request_id))
    query = (query.filter(MoleculeForecastParameter.sku_row_id.is_(None))
             if params.sku_row_id is None
             else query.filter(MoleculeForecastParameter.sku_row_id == params.sku_row_id))
    # Row lock on PostgreSQL; a no-op on SQLite, where the whole write is serialized anyway.
    row = query.with_for_update().one_or_none()

    if row is None:
        if payload.revision != 0:
            raise HTTPException(
                409, "No saved forecast exists for this configuration; send revision 0 to create it.")
        row = MoleculeForecastParameter(
            request_id=payload.request_id, sku_row_id=params.sku_row_id, revision=1)
        _apply(row, params)
        row.updated_at = _now()
        row.updated_by = user.id
        db.add(row)
        db.flush()
    else:
        if payload.revision != row.revision:
            raise HTTPException(
                409, f"This forecast was updated by someone else (stored revision "
                     f"{row.revision}, you sent {payload.revision}). Reload and reapply "
                     "your changes.")
        _apply(row, params)
        row.revision += 1
        row.updated_at = _now()
        row.updated_by = user.id
        db.flush()

    db.add(MoleculeForecastAudit(
        parameter_id=row.id, request_id=row.request_id, revision=row.revision,
        payload=_assumption_summary(row), change_reason=payload.change_reason,
        changed_by=user.id, changed_at=_now()))
    db.commit()
    db.refresh(row)
    return load_collection(db, payload.request_id)


def persist_observations(db: Session, request_id: int, user_id: int,
                         observations: list[Observation]) -> list[MoleculeSourceObservation]:
    """Store imported/fetched evidence beside the request.

    Deliberately does not touch MoleculeForecastParameter: ingestion never overwrites a
    reviewed assumption. Adopting an observation is a separate, explicit upsert.
    """
    stored = []
    for obs in observations:
        row = MoleculeSourceObservation(
            request_id=request_id, source_kind=obs.source_kind.value, source_url=obs.source_url,
            source_identifier=obs.source_identifier, molecule=obs.molecule, brand=obs.brand,
            geography=obs.geography, coverage=obs.coverage, period_label=obs.period_label,
            period_start=obs.period_start, period_end=obs.period_end, metric=obs.metric.value,
            value=obs.value, unit=obs.unit, strength=obs.strength, dosage_form=obs.dosage_form,
            currency=obs.currency, transformation=obs.transformation,
            ambiguous_match=obs.ambiguous_match, retrieved_at=obs.retrieved_at,
            raw_record=obs.raw_record, created_by=user_id,
            provenance_class=obs.provenance_class.value, retrieval_url=obs.retrieval_url,
            archive_capture_date=obs.archive_capture_date, content_sha256=obs.content_sha256,
            file_verification=obs.file_verification.value if obs.file_verification else None)
        db.add(row)
        stored.append(row)
    db.commit()
    for row in stored:
        db.refresh(row)
    return stored


def aware(value: dt.datetime | None) -> dt.datetime | None:
    """Public alias of the tz-normalising helper, for the API layer."""
    return _aware(value)


def _cms_observations(db: Session, request_id: int):
    return (db.query(MoleculeSourceObservation)
            .filter(MoleculeSourceObservation.request_id == request_id,
                    MoleculeSourceObservation.source_kind == SourceKind.CMS_PART_D.value))


def latest_cms_observation(db: Session, request_id: int) -> MoleculeSourceObservation | None:
    """The most recently retrieved CMS figure for this request, whatever the route.

    This is what "last successful refresh" means here: the last time a CMS number was
    actually taken in, not the last time someone opened the panel.
    """
    return (_cms_observations(db, request_id)
            .order_by(MoleculeSourceObservation.retrieved_at.desc(),
                      MoleculeSourceObservation.id.desc())
            .first())


def count_cms_observations(db: Session, request_id: int) -> int:
    return _cms_observations(db, request_id).count()
