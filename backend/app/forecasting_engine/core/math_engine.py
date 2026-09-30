"""Deterministic 10-year molecule volume projections.

Pure functions only: no database, no network, no language-model call, no clock and
no randomness. The same arguments always produce the same trajectories, which is what
makes a saved forecast auditable a year later.

The adoption curve is the logistic supplied in the specification:

    adoption(t) = expit(ramp_speed * (t - inflection_year))

`peak_share` is the ASYMPTOTE that adoption approaches, not a value that is
necessarily attained inside the 10-year window: at t == inflection_year adoption is
exactly 0.5, and it tends to 1 only as t grows without bound. This is a plain logistic
uptake curve, NOT Bass diffusion — there is no innovation/imitation split here.

All patient figures are ANNUAL TREATED PATIENTS in the year concerned, never a
cumulative count of unique patients ever treated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from scipy.special import expit

from app.forecasting_engine.core.units import ForecastMode

#: Every scenario array returned by this module has exactly this many entries.
HORIZON_YEARS = 10

#: Bumped whenever a change here would alter the numbers for unchanged inputs.
#: Persisted next to each parameter set so a stored forecast can be traced to the
#: engine that produced it.
MODEL_VERSION = "1.0.0"

#: Documented inflection-year bounds. Below the minimum the curve is already at its
#: asymptote in year 1 (a step, not a ramp); above the maximum essentially nothing
#: happens inside a 10-year window. Both extremes are far likelier to be a data-entry
#: slip than a real assumption, so they are rejected rather than silently modelled.
INFLECTION_YEAR_MIN = 0.5
INFLECTION_YEAR_MAX = 15.0

#: ramp_speed must be > 0. Above this the curve is indistinguishable from a step
#: change between adjacent years — allowed, but warned about rather than rejected.
RAMP_SPEED_WARN_ABOVE = 5.0


class ForecastInputError(ValueError):
    """Raised when arguments cannot produce a meaningful forecast.

    The API layer turns this into a 422; it is never swallowed into a default value.
    """


def _finite(name: str, value: float) -> float:
    """Reject NaN and infinity at the numeric boundary.

    Pydantic already rejects them on the way in, but the math engine is also called
    directly by tests and services, and a NaN that reaches NumPy propagates silently
    through every downstream metric instead of failing loudly.
    """
    coerced = float(value)
    if not math.isfinite(coerced):
        raise ForecastInputError(f"{name} must be a finite number, got {value!r}")
    return coerced


def _nonnegative(name: str, value: float) -> float:
    coerced = _finite(name, value)
    if coerced < 0:
        raise ForecastInputError(f"{name} must be >= 0, got {coerced!r}")
    return coerced


def _share(name: str, value: float) -> float:
    coerced = _finite(name, value)
    if not 0.0 <= coerced <= 1.0:
        raise ForecastInputError(f"{name} must be between 0 and 1 inclusive, got {coerced!r}")
    return coerced


def _positive(name: str, value: float) -> float:
    coerced = _finite(name, value)
    if coerced <= 0:
        raise ForecastInputError(f"{name} must be > 0, got {coerced!r}")
    return coerced


def validate_curve_arguments(ramp_speed: float, inflection_year: float) -> None:
    """Check the two shape arguments shared by both modes."""
    _positive("ramp_speed", ramp_speed)
    inflection = _finite("inflection_year", inflection_year)
    if not INFLECTION_YEAR_MIN <= inflection <= INFLECTION_YEAR_MAX:
        raise ForecastInputError(
            f"inflection_year must be between {INFLECTION_YEAR_MIN} and "
            f"{INFLECTION_YEAR_MAX} inclusive, got {inflection!r}"
        )


def forecast_calendar_years(forecast_start_year: int) -> list[int]:
    """The 10 calendar years a forecast covers, starting at forecast_start_year."""
    return [int(forecast_start_year) + offset for offset in range(HORIZON_YEARS)]


def years_since_launch(calendar_years: list[int], launch_year: int) -> np.ndarray:
    """t for each calendar year, where t == 1 is the first year after launch.

    Values <= 0 are prelaunch. They are kept (rather than clipped) so callers can tell
    a prelaunch zero apart from a modelled zero.
    """
    return np.asarray(calendar_years, dtype=float) - float(launch_year) + 1.0


def adoption_curve(ramp_speed: float, inflection_year: float, t: np.ndarray) -> np.ndarray:
    """adoption(t) = expit(ramp_speed * (t - inflection_year)), zeroed before launch.

    The forecast is conditional on launch: in calendar years at or before launch_year
    (t <= 0) adoption is exactly 0, so every derived volume in those years is 0 rather
    than a small positive number from the tail of the logistic.
    """
    validate_curve_arguments(ramp_speed, inflection_year)
    curve = expit(float(ramp_speed) * (t - float(inflection_year)))
    return np.where(t >= 1.0, curve, 0.0)


@dataclass(frozen=True)
class ConversionAssumptions:
    """Explicit unit-conversion and capture assumptions.

    Every field is optional. A missing field means the metrics that depend on it are
    returned as null — the engine never substitutes a default, because a guessed
    units_per_patient_per_year silently rescales the entire forecast.
    """

    units_per_patient_per_year: float | None = None
    units_per_pack: float | None = None
    active_ingredient_mg_per_unit: float | None = None
    #: Epidemiology mode only: our company's commercial capture of the modelled
    #: product's demand. Applied EXACTLY ONCE, on top of the product's patient share.
    #: In observed-volume mode the capture share is peak_capture_share itself and this
    #: field must be None, or capture would be applied twice.
    company_capture_share: float | None = None

    def validate(self, mode: ForecastMode) -> None:
        if self.units_per_patient_per_year is not None:
            _positive("units_per_patient_per_year", self.units_per_patient_per_year)
        if self.units_per_pack is not None:
            _positive("units_per_pack", self.units_per_pack)
        if self.active_ingredient_mg_per_unit is not None:
            _positive("active_ingredient_mg_per_unit", self.active_ingredient_mg_per_unit)
        if self.company_capture_share is not None:
            _share("company_capture_share", self.company_capture_share)
            if mode is ForecastMode.OBSERVED_VOLUME:
                raise ForecastInputError(
                    "company_capture_share must not be set in observed_volume mode: "
                    "peak_capture_share already is the company capture, and applying "
                    "both would count it twice"
                )


@dataclass(frozen=True)
class ScenarioTrajectory:
    """One scenario (base or upside) over the 10 calendar years of the window.

    Arrays are unrounded float64 lists of exactly HORIZON_YEARS entries. A metric whose
    conversion inputs are absent is None for the whole scenario — never a list of zeros.

    `addressable_*` is total demand in the modelled market; `business_*` is our
    obtainable volume after the capture share. They are deliberately separate fields so
    the UI can never present one as the other.
    """

    addressable_patients: list[float] | None
    patients: list[float] | None
    addressable_dosage_units: list[float] | None
    business_dosage_units: list[float] | None
    business_packs: list[float] | None
    business_api_kg: list[float] | None
    business_revenue: list[Decimal] | None


def _as_list(array: np.ndarray) -> list[float]:
    values = [float(v) for v in np.asarray(array, dtype=float)]
    if len(values) != HORIZON_YEARS:
        raise ForecastInputError(
            f"scenario must contain exactly {HORIZON_YEARS} values, got {len(values)}"
        )
    for value in values:
        if not math.isfinite(value):
            raise ForecastInputError("scenario produced a non-finite value")
    return values


def _derive_units(
    driver_units: np.ndarray | None,
    conversions: ConversionAssumptions,
) -> tuple[list[float] | None, list[float] | None]:
    """packs and contained-API mass from a dosage-unit series.

    api_kg is CONTAINED ACTIVE INGREDIENT demand, not a manufacturing input
    requirement: it applies no yield, salt-factor or potency adjustment. Those need
    their own explicit factors and are out of scope here.
    """
    if driver_units is None:
        return None, None
    packs = None
    if conversions.units_per_pack is not None:
        packs = _as_list(driver_units / float(conversions.units_per_pack))
    api_kg = None
    if conversions.active_ingredient_mg_per_unit is not None:
        api_kg = _as_list(
            driver_units * float(conversions.active_ingredient_mg_per_unit) / 1_000_000.0
        )
    return packs, api_kg


def epidemiology_scenario(
    *,
    target_population: float,
    peak_share: float,
    ramp_speed: float,
    inflection_year: float,
    calendar_years: list[int],
    launch_year: int,
    conversions: ConversionAssumptions,
) -> ScenarioTrajectory:
    """Annual treated patients and derived volumes from an eligible population.

    target_population (N) is the annual eligible, addressable patient population for
    one geography and one indication. Whether it is a prevalence or an incidence
    population, and whether a patient means chronic therapy or one annual course, is
    recorded alongside it by the caller — this function does not and cannot infer it.

        patients_s(t) = N * peak_share_s * adoption(t)

    peak_share is the modelled product's asymptotic share OF PATIENTS. Our company's
    commercial capture, if any, is a separate factor applied once to the derived
    dosage units.
    """
    population = _nonnegative("target_population", target_population)
    share = _share("peak_share", peak_share)
    conversions.validate(ForecastMode.EPIDEMIOLOGY)

    t = years_since_launch(calendar_years, launch_year)
    adoption = adoption_curve(ramp_speed, inflection_year, t)
    patients = population * share * adoption

    # Held flat across the window: no epidemiological growth assumption is applied,
    # because none was supplied. Growing it would invent a trend.
    addressable_patients = np.full(len(calendar_years), population, dtype=float)

    product_units = None
    business_units = None
    if conversions.units_per_patient_per_year is not None:
        product_units = patients * float(conversions.units_per_patient_per_year)
        if conversions.company_capture_share is not None:
            business_units = product_units * float(conversions.company_capture_share)

    addressable_units = None
    if conversions.units_per_patient_per_year is not None:
        addressable_units = addressable_patients * float(conversions.units_per_patient_per_year)

    packs, api_kg = _derive_units(business_units, conversions)
    return ScenarioTrajectory(
        addressable_patients=_as_list(addressable_patients),
        patients=_as_list(patients),
        addressable_dosage_units=None if addressable_units is None else _as_list(addressable_units),
        business_dosage_units=None if business_units is None else _as_list(business_units),
        business_packs=packs,
        business_api_kg=api_kg,
        business_revenue=None,
    )


def observed_volume_scenario(
    *,
    reference_units: float,
    reference_year: int,
    annual_growth_rate: float,
    peak_capture_share: float,
    ramp_speed: float,
    inflection_year: float,
    calendar_years: list[int],
    launch_year: int,
    conversions: ConversionAssumptions,
) -> ScenarioTrajectory:
    """Our obtainable volume against an observed historical market baseline.

        market_units(t)      = reference_units * (1 + annual_growth_rate) ** elapsed_years
        business_units_s(t)  = market_units(t) * peak_capture_share_s * adoption(t)

    elapsed_years runs from the REFERENCE DATA YEAR to each calendar year, so the
    baseline is grown from the year it was actually measured in.

    The market series inherits the coverage of its source: if reference_units came from
    a covered subpopulation, so does every number here. This function never scales that
    up to a national or global market — a coverage factor must be applied upstream,
    explicitly and on the record.

    There is no patient population in this mode, and none is multiplied in.
    """
    baseline = _nonnegative("reference_units", reference_units)
    growth = _finite("annual_growth_rate", annual_growth_rate)
    if growth <= -1.0:
        raise ForecastInputError(f"annual_growth_rate must be > -1, got {growth!r}")
    capture = _share("peak_capture_share", peak_capture_share)
    conversions.validate(ForecastMode.OBSERVED_VOLUME)

    elapsed = np.asarray(calendar_years, dtype=float) - float(reference_year)
    market_units = baseline * np.power(1.0 + growth, elapsed)

    t = years_since_launch(calendar_years, launch_year)
    adoption = adoption_curve(ramp_speed, inflection_year, t)
    business_units = market_units * capture * adoption

    packs, api_kg = _derive_units(business_units, conversions)
    return ScenarioTrajectory(
        addressable_patients=None,
        patients=None,
        addressable_dosage_units=_as_list(market_units),
        business_dosage_units=_as_list(business_units),
        business_packs=packs,
        business_api_kg=api_kg,
        business_revenue=None,
    )


def scenario_revenue(
    trajectory: ScenarioTrajectory,
    net_price: Decimal,
    priced_metric_values: list[float] | None,
) -> list[Decimal] | None:
    """Revenue = business volume in the priced unit * net price per that SAME unit.

    Money is Decimal end to end. Returns None when the priced metric is unavailable,
    so an absent pack count can never quietly become zero revenue.
    """
    if priced_metric_values is None:
        return None
    if not isinstance(net_price, Decimal):
        raise ForecastInputError("net_price must be a Decimal")
    return [Decimal(repr(value)) * net_price for value in priced_metric_values]


def apply_probability_of_success(
    values: list[float] | None, probability_of_success: float
) -> list[float] | None:
    """Risk-adjust a scenario.

    Returned as a SEPARATE series by the caller: the base and upside arrays stay
    conditional on launch, which is what makes them comparable across deals.
    """
    probability = _share("probability_of_success", probability_of_success)
    if values is None:
        return None
    return [value * probability for value in values]
