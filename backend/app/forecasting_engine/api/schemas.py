"""Request and response shapes for the forecasting API.

Strict on the way in: unknown fields are rejected rather than ignored, every float
must be finite, and mode-specific fields are required or forbidden according to the
mode. A request that cannot produce a defensible forecast fails loudly at the edge.
"""
from __future__ import annotations

import datetime as dt
import math
from decimal import Decimal
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.forecasting_engine.core.math_engine import (HORIZON_YEARS, INFLECTION_YEAR_MAX,
                                                      INFLECTION_YEAR_MIN, RAMP_SPEED_WARN_ABOVE)
from app.forecasting_engine.core.units import (ApiConnectivity, FileVerificationStatus,
                                                ForecastMode, PopulationBasis, PriceBasis,
                                                ProvenanceClass, PublicationFreshness,
                                                SourceKind, SourceMetric, TreatmentBasis,
                                                is_valid_currency_code)
from app.forecasting_engine.services.sources.base import SourceStatus

#: Documented calendar bounds. Wide enough for any real deal, narrow enough that a
#: mistyped year is rejected instead of producing a forecast starting in year 202.
MIN_YEAR = 2000
MAX_YEAR = 2100


class StrictModel(BaseModel):
    """Rejects unknown fields everywhere in this API."""

    model_config = ConfigDict(extra="forbid")


def _check_finite(value: Optional[float], field: str) -> Optional[float]:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


class ForecastParametersIn(StrictModel):
    """A complete parameter set. Partial updates are not accepted: the client sends the
    whole reviewed configuration, which is what makes revision-based concurrency sound."""

    sku_row_id: Optional[int] = None

    molecule: str = Field(min_length=1, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=200)
    geography: str = Field(min_length=1, max_length=50)
    indication: Optional[str] = Field(default=None, max_length=200)
    strength: Optional[str] = Field(default=None, max_length=50)
    dosage_form: Optional[str] = Field(default=None, max_length=100)

    forecast_start_year: int = Field(ge=MIN_YEAR, le=MAX_YEAR)
    launch_year: int = Field(ge=MIN_YEAR, le=MAX_YEAR)
    forecast_mode: ForecastMode

    target_population: Optional[int] = Field(default=None, ge=0)
    population_basis: Optional[PopulationBasis] = None
    treatment_basis: Optional[TreatmentBasis] = None

    reference_units: Optional[int] = Field(default=None, ge=0)
    reference_year: Optional[int] = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    annual_growth_rate: Optional[float] = None
    reference_coverage_note: Optional[str] = Field(default=None, max_length=2000)

    base_peak_share: float = Field(ge=0, le=1)
    upside_peak_share: float = Field(ge=0, le=1)
    ramp_speed: float = Field(gt=0)
    inflection_year: float = Field(ge=INFLECTION_YEAR_MIN, le=INFLECTION_YEAR_MAX)

    units_per_patient_per_year: Optional[float] = Field(default=None, gt=0)
    units_per_patient_basis: Optional[str] = Field(default=None, max_length=2000)
    units_per_pack: Optional[float] = Field(default=None, gt=0)
    active_ingredient_mg_per_unit: Optional[float] = Field(default=None, gt=0)
    company_capture_share: Optional[float] = Field(default=None, ge=0, le=1)
    probability_of_success: Optional[float] = Field(default=None, ge=0, le=1)

    net_price: Optional[Decimal] = Field(default=None, ge=0)
    price_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    price_basis: Optional[PriceBasis] = None

    source_observation_id: Optional[int] = None
    override_reason: Optional[str] = Field(default=None, max_length=500)
    overridden_source_value: Optional[float] = None

    @field_validator("annual_growth_rate")
    @classmethod
    def _growth_above_negative_one(cls, v: Optional[float]) -> Optional[float]:
        _check_finite(v, "annual_growth_rate")
        if v is not None and v <= -1:
            raise ValueError("annual_growth_rate must be greater than -1")
        return v

    @field_validator("base_peak_share", "upside_peak_share", "ramp_speed", "inflection_year",
                     "units_per_patient_per_year", "units_per_pack",
                     "active_ingredient_mg_per_unit", "company_capture_share",
                     "probability_of_success", "overridden_source_value")
    @classmethod
    def _finite(cls, v: Optional[float]) -> Optional[float]:
        return _check_finite(v, "value")

    @field_validator("price_currency")
    @classmethod
    def _currency_shape(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        upper = v.upper()
        if not is_valid_currency_code(upper):
            raise ValueError("price_currency must be a 3-letter ISO 4217 code, e.g. USD")
        return upper

    @model_validator(mode="after")
    def _check_consistency(self) -> "ForecastParametersIn":
        if self.base_peak_share > self.upside_peak_share:
            raise ValueError("base_peak_share must not exceed upside_peak_share")
        if self.launch_year < self.forecast_start_year - HORIZON_YEARS:
            raise ValueError(
                "launch_year is more than one forecast horizon before forecast_start_year, "
                "so the window would contain no adoption at all")

        if self.forecast_mode is ForecastMode.EPIDEMIOLOGY:
            if self.target_population is None:
                raise ValueError("epidemiology mode requires target_population")
            if self.population_basis is None:
                raise ValueError(
                    "epidemiology mode requires population_basis: state whether "
                    "target_population is a prevalence or an incidence population — "
                    "the two are never mixed automatically")
            if self.treatment_basis is None:
                raise ValueError(
                    "epidemiology mode requires treatment_basis: state whether a treated "
                    "patient means chronic therapy or one annual treatment course")
            for forbidden in ("reference_units", "reference_year"):
                if getattr(self, forbidden) is not None:
                    raise ValueError(f"{forbidden} belongs to observed_volume mode only")
        else:
            for required in ("reference_units", "reference_year", "annual_growth_rate"):
                if getattr(self, required) is None:
                    raise ValueError(f"observed_volume mode requires {required}")
            if self.target_population is not None:
                raise ValueError(
                    "target_population belongs to epidemiology mode only: observed-volume "
                    "forecasts are never multiplied by a patient population")
            if self.company_capture_share is not None:
                raise ValueError(
                    "company_capture_share belongs to epidemiology mode only: in "
                    "observed_volume mode peak_capture_share already is the company "
                    "capture, and applying both would count it twice")

        price_fields = (self.net_price, self.price_currency, self.price_basis)
        if any(f is not None for f in price_fields) and not all(f is not None for f in price_fields):
            raise ValueError(
                "net_price, price_currency and price_basis must be supplied together: "
                "a price without a currency and a stated basis is not interpretable")

        if self.overridden_source_value is not None and not self.override_reason:
            raise ValueError("an override requires override_reason")
        return self


class ForecastUpsertIn(StrictModel):
    """An upsert carries the revision the client last read, for optimistic concurrency.

    revision=0 means "I am creating this"; a mismatch against the stored revision is a
    409, never a silent overwrite of someone else's edit.
    """

    request_id: int
    revision: int = Field(ge=0)
    change_reason: Optional[str] = Field(default=None, max_length=500)
    parameters: ForecastParametersIn


class ObservationOut(StrictModel):
    id: Optional[int] = None
    source_kind: SourceKind
    source_url: Optional[str] = None
    source_identifier: Optional[str] = None
    molecule: Optional[str] = None
    brand: Optional[str] = None
    geography: str
    coverage: str
    period_label: str
    metric: SourceMetric
    unit: str
    value: Optional[Decimal] = None
    currency: Optional[str] = None
    strength: Optional[str] = None
    dosage_form: Optional[str] = None
    transformation: str
    ambiguous_match: bool = False
    retrieved_at: dt.datetime
    stale: bool = False
    #: How the bytes reached us, kept distinct from who published them.
    provenance_class: ProvenanceClass = ProvenanceClass.USER_SUPPLIED_FILE
    retrieval_url: Optional[str] = None
    archive_capture_date: Optional[dt.datetime] = None
    content_sha256: Optional[str] = None


class SourceSearchOut(StrictModel):
    """Search never modifies approved parameters; it only reports what is out there.

    `status` distinguishes the three non-results the UI must not conflate: the source is
    unreachable, this deployment is not configured, or the source answered and has no
    such drug. Only the last says anything about the molecule.
    """

    query_echo: dict
    results: list[ObservationOut]
    available: bool
    status: SourceStatus
    unavailable_reason: Optional[str] = None
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class CmsFileIngestIn(StrictModel):
    """Ingest the official CMS bulk CSV download for a request.

    `payload` is the file's text. Provenance is taken from the verified descriptor (the
    CMS URL the file is published at), and `retrieval_note` records how this copy was
    obtained so the observation stays auditable.
    """

    request_id: int
    payload: str = Field(min_length=1)
    molecule: Optional[str] = Field(default=None, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=200)
    data_year: Optional[int] = Field(default=None, ge=MIN_YEAR, le=MAX_YEAR)
    retrieval_note: str = Field(default="official CMS CSV download", max_length=500)
    #: Where these bytes were actually fetched from, when that is not the CMS publication
    #: URL. Supplying it records the ingest as an archived CMS publication.
    retrieval_url: Optional[str] = Field(default=None, max_length=2000)
    archive_capture_date: Optional[dt.datetime] = None

    @model_validator(mode="after")
    def _needs_a_query(self) -> "CmsFileIngestIn":
        if not (self.molecule or self.brand):
            raise ValueError("provide a molecule or brand to select rows from the CMS file")
        return self


class SourceImportIn(StrictModel):
    request_id: int
    format: Literal["csv", "json"]
    payload: Optional[str] = None
    rows: Optional[list[dict]] = None

    @model_validator(mode="after")
    def _one_payload(self) -> "SourceImportIn":
        if (self.payload is None) == (self.rows is None):
            raise ValueError("supply exactly one of payload (csv text) or rows (json records)")
        if self.format == "csv" and self.payload is None:
            raise ValueError("csv format requires payload")
        if self.format == "json" and self.rows is None:
            raise ValueError("json format requires rows")
        return self


Series = Annotated[list[float], Field(min_length=HORIZON_YEARS, max_length=HORIZON_YEARS)]


class ScenarioOut(StrictModel):
    """One scenario. Every present series holds exactly HORIZON_YEARS values; a metric
    whose inputs are absent is null rather than an array of zeros."""

    addressable_patients: Optional[Series] = None
    patients: Optional[Series] = None
    addressable_dosage_units: Optional[Series] = None
    business_dosage_units: Optional[Series] = None
    business_packs: Optional[Series] = None
    business_api_kg: Optional[Series] = None
    business_revenue: Optional[list[Decimal]] = None
    #: Present only when probability_of_success was supplied. Kept separate so the
    #: scenario arrays above stay conditional on launch.
    risk_adjusted_business_dosage_units: Optional[Series] = None


class UnitMetadata(StrictModel):
    patients: Optional[str] = None
    dosage_units: Optional[str] = None
    packs: Optional[str] = None
    api_kg: Optional[str] = None
    revenue: Optional[str] = None


class ForecastOut(StrictModel):
    deal_id: int
    request_id: int
    sku_row_id: Optional[int] = None
    revision: int
    model_version: str
    forecast_mode: ForecastMode
    calendar_years: list[int]
    base_case: ScenarioOut
    upside_case: ScenarioOut
    unit_metadata: UnitMetadata
    assumption_summary: dict
    source_references: list[ObservationOut]
    updated_at: dt.datetime
    warnings: list[str] = Field(default_factory=list)


class ForecastCollectionOut(StrictModel):
    """A request's forecasts. One request-level entry, or one per SKU — never both, so
    the entries can be summed without double-counting."""

    request_id: int
    granularity: Literal["request", "sku", "none"]
    forecasts: list[ForecastOut]
    warnings: list[str] = Field(default_factory=list)


class CmsSourceStatusOut(StrictModel):
    """Three independent facts about the CMS source, never collapsed into one flag.

    A deployment can hold a verified file of the current reporting year and still have no
    API connectivity; it can have connectivity and an unrecognised file. Each is reported
    on its own so the reader can tell which one needs attention.
    """

    dataset_title: str
    publication_url: str
    reporting_year: Optional[int] = None
    latest_published_year: int

    #: 1. Does the ingested file match the copy that was verified by hand?
    file_verification: Optional[FileVerificationStatus] = None
    file_sha256: Optional[str] = None

    #: 2. Is the reporting year the newest CMS is known to have published?
    #: Never "current" on a configured constant alone — it depends on a recent successful
    #: metadata check, and degrades to unknown when one is missing or stale.
    publication_freshness: PublicationFreshness
    published_on: Optional[dt.date] = None
    last_metadata_check_at: Optional[dt.datetime] = None
    last_metadata_check_status: Optional[str] = None
    metadata_check_detail: Optional[str] = None
    new_release_detected: bool = False
    #: Plain-language label for the UI. States the reporting year and says, in words, that
    #: it is not current-year observed sales.
    freshness_label: str = ""

    #: Release registry — checksum identity is separate from source validation.
    active_release_status: Optional[str] = None
    active_release_validated_at: Optional[dt.datetime] = None
    active_release_checks: Optional[list[dict]] = None

    #: 3. Can this deployment reach the live CMS API right now?
    api_connectivity: ApiConnectivity
    api_endpoint: str
    api_http_status: Optional[int] = None
    api_checked_at: Optional[dt.datetime] = None
    akamai_reference: Optional[str] = None
    api_detail: Optional[str] = None
    support_summary: Optional[str] = None

    #: When this request last took a successful figure from this source, whatever the route.
    last_successful_refresh: Optional[dt.datetime] = None
    last_refresh_provenance: Optional[ProvenanceClass] = None
    retrieval_url: Optional[str] = None
    archive_capture_date: Optional[dt.datetime] = None
    observation_count: int = 0
