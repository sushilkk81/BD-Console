import math
from decimal import Decimal

import numpy as np
import pytest

from app.forecasting_engine.core import math_engine as me
from app.forecasting_engine.core.units import ForecastMode

BASE_CURVE = {"ramp_speed": 0.8, "inflection_year": 4.0}


def calendar(start=2027):
    return me.forecast_calendar_years(start)


def conversions(**kwargs):
    return me.ConversionAssumptions(**kwargs)


def test_adoption_is_exactly_one_half_at_the_inflection_year():
    t = np.array([4.0])
    adoption = me.adoption_curve(ramp_speed=0.8, inflection_year=4.0, t=t)
    assert adoption[0] == pytest.approx(0.5, abs=1e-12)


def test_adoption_matches_the_logistic_by_hand():
    t = np.array([1.0, 7.0])
    adoption = me.adoption_curve(ramp_speed=0.8, inflection_year=4.0, t=t)
    assert adoption[0] == pytest.approx(1 / (1 + math.exp(-0.8 * (1 - 4))), rel=1e-12)
    assert adoption[1] == pytest.approx(1 / (1 + math.exp(-0.8 * (7 - 4))), rel=1e-12)


def test_adoption_is_monotonically_increasing_and_never_reaches_peak_share():
    t = np.arange(1.0, 11.0)
    adoption = me.adoption_curve(ramp_speed=0.8, inflection_year=4.0, t=t)
    assert list(adoption) == sorted(adoption)
    # peak_share is asymptotic: adoption is strictly below 1 even in year 10.
    assert adoption[-1] < 1.0


def test_scenario_has_exactly_ten_finite_unrounded_values():
    result = me.epidemiology_scenario(
        target_population=1_000_000, peak_share=0.2, calendar_years=calendar(),
        launch_year=2027, conversions=conversions(), **BASE_CURVE,
    )
    assert len(result.patients) == 10
    assert all(math.isfinite(v) for v in result.patients)
    # Unrounded: a rounded series would be integral here.
    assert any(v != round(v) for v in result.patients)


def test_prelaunch_calendar_years_are_zero_and_later_years_are_not():
    result = me.epidemiology_scenario(
        target_population=1_000_000, peak_share=0.2, calendar_years=calendar(2027),
        launch_year=2030, conversions=conversions(), **BASE_CURVE,
    )
    # 2027, 2028, 2029 precede launch; 2030 is launch year itself (t == 1).
    assert result.patients[:3] == [0.0, 0.0, 0.0]
    assert result.patients[3] > 0.0


def test_zero_population_gives_an_all_zero_patient_trajectory():
    result = me.epidemiology_scenario(
        target_population=0, peak_share=0.4, calendar_years=calendar(),
        launch_year=2027, conversions=conversions(), **BASE_CURVE,
    )
    assert result.patients == [0.0] * 10


def test_upside_is_never_below_base_under_shared_curve_assumptions():
    shared = dict(target_population=500_000, calendar_years=calendar(), launch_year=2027,
                  conversions=conversions(), **BASE_CURVE)
    base = me.epidemiology_scenario(peak_share=0.10, **shared)
    upside = me.epidemiology_scenario(peak_share=0.25, **shared)
    assert all(u >= b for b, u in zip(base.patients, upside.patients))


def test_unit_conversions_chain_from_patients_to_packs_and_api_kg():
    result = me.epidemiology_scenario(
        target_population=100_000, peak_share=0.5, calendar_years=calendar(),
        launch_year=2027,
        conversions=conversions(units_per_patient_per_year=52, units_per_pack=4,
                                active_ingredient_mg_per_unit=2.5,
                                company_capture_share=0.3),
        **BASE_CURVE,
    )
    for patients, units, packs, kg in zip(result.patients, result.business_dosage_units,
                                          result.business_packs, result.business_api_kg):
        assert units == pytest.approx(patients * 52 * 0.3)
        assert packs == pytest.approx(units / 4)
        assert kg == pytest.approx(units * 2.5 / 1_000_000)


def test_missing_conversion_inputs_yield_null_metrics_not_zeros():
    result = me.epidemiology_scenario(
        target_population=100_000, peak_share=0.5, calendar_years=calendar(),
        launch_year=2027, conversions=conversions(units_per_patient_per_year=12),
        **BASE_CURVE,
    )
    assert result.business_dosage_units is None  # no company capture share supplied
    assert result.business_packs is None
    assert result.business_api_kg is None


def test_company_capture_is_applied_exactly_once():
    shared = dict(target_population=100_000, peak_share=0.5, calendar_years=calendar(),
                  launch_year=2027, **BASE_CURVE)
    uncaptured = me.epidemiology_scenario(
        conversions=conversions(units_per_patient_per_year=10, company_capture_share=1.0), **shared)
    captured = me.epidemiology_scenario(
        conversions=conversions(units_per_patient_per_year=10, company_capture_share=0.25), **shared)
    for full, part in zip(uncaptured.business_dosage_units, captured.business_dosage_units):
        assert part == pytest.approx(full * 0.25)


def test_observed_mode_grows_the_baseline_from_its_reference_year():
    years = calendar(2027)
    result = me.observed_volume_scenario(
        reference_units=1_000_000, reference_year=2025, annual_growth_rate=0.10,
        peak_capture_share=0.2, calendar_years=years, launch_year=2027,
        conversions=conversions(), **BASE_CURVE,
    )
    # 2027 is two years after the 2025 reference year.
    assert result.addressable_dosage_units[0] == pytest.approx(1_000_000 * 1.10 ** 2)
    assert result.addressable_dosage_units[-1] == pytest.approx(1_000_000 * 1.10 ** 11)


def test_observed_mode_business_units_are_market_times_capture_times_adoption():
    years = calendar(2027)
    result = me.observed_volume_scenario(
        reference_units=2_000_000, reference_year=2027, annual_growth_rate=0.0,
        peak_capture_share=0.3, calendar_years=years, launch_year=2027,
        conversions=conversions(), **BASE_CURVE,
    )
    t = me.years_since_launch(years, 2027)
    adoption = me.adoption_curve(t=t, **BASE_CURVE)
    for got, want in zip(result.business_dosage_units, 2_000_000 * 0.3 * adoption):
        assert got == pytest.approx(want)


def test_observed_mode_reports_no_patient_series():
    result = me.observed_volume_scenario(
        reference_units=1_000, reference_year=2025, annual_growth_rate=0.0,
        peak_capture_share=0.5, calendar_years=calendar(), launch_year=2027,
        conversions=conversions(), **BASE_CURVE,
    )
    assert result.patients is None
    assert result.addressable_patients is None


def test_observed_mode_rejects_a_second_company_capture_factor():
    with pytest.raises(me.ForecastInputError, match="twice"):
        me.observed_volume_scenario(
            reference_units=1_000, reference_year=2025, annual_growth_rate=0.0,
            peak_capture_share=0.5, calendar_years=calendar(), launch_year=2027,
            conversions=conversions(company_capture_share=0.4), **BASE_CURVE,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_population_is_rejected(bad):
    with pytest.raises(me.ForecastInputError, match="finite"):
        me.epidemiology_scenario(
            target_population=bad, peak_share=0.2, calendar_years=calendar(),
            launch_year=2027, conversions=conversions(), **BASE_CURVE,
        )


def test_negative_population_is_rejected():
    with pytest.raises(me.ForecastInputError, match=">= 0"):
        me.epidemiology_scenario(
            target_population=-1, peak_share=0.2, calendar_years=calendar(),
            launch_year=2027, conversions=conversions(), **BASE_CURVE,
        )


@pytest.mark.parametrize("ramp", [0.0, -1.0])
def test_non_positive_ramp_speed_is_rejected(ramp):
    with pytest.raises(me.ForecastInputError, match="ramp_speed"):
        me.adoption_curve(ramp_speed=ramp, inflection_year=4.0, t=np.array([1.0]))


@pytest.mark.parametrize("inflection", [me.INFLECTION_YEAR_MIN - 0.1, me.INFLECTION_YEAR_MAX + 0.1])
def test_out_of_bounds_inflection_year_is_rejected(inflection):
    with pytest.raises(me.ForecastInputError, match="inflection_year"):
        me.adoption_curve(ramp_speed=1.0, inflection_year=inflection, t=np.array([1.0]))


def test_growth_rate_of_negative_one_or_worse_is_rejected():
    with pytest.raises(me.ForecastInputError, match="annual_growth_rate"):
        me.observed_volume_scenario(
            reference_units=1_000, reference_year=2025, annual_growth_rate=-1.0,
            peak_capture_share=0.5, calendar_years=calendar(), launch_year=2027,
            conversions=conversions(), **BASE_CURVE,
        )


def test_zero_units_per_pack_is_rejected_rather_than_dividing_by_zero():
    with pytest.raises(me.ForecastInputError, match="units_per_pack"):
        conversions(units_per_pack=0).validate(ForecastMode.EPIDEMIOLOGY)


def test_revenue_is_decimal_and_null_when_the_priced_metric_is_missing():
    result = me.epidemiology_scenario(
        target_population=1_000, peak_share=0.5, calendar_years=calendar(),
        launch_year=2027,
        conversions=conversions(units_per_patient_per_year=10, company_capture_share=0.5),
        **BASE_CURVE,
    )
    revenue = me.scenario_revenue(result, Decimal("12.50"), result.business_dosage_units)
    assert all(isinstance(v, Decimal) for v in revenue)
    assert revenue[0] == Decimal(repr(result.business_dosage_units[0])) * Decimal("12.50")
    assert me.scenario_revenue(result, Decimal("12.50"), result.business_packs) is None


def test_probability_of_success_is_a_separate_multiplication():
    result = me.epidemiology_scenario(
        target_population=1_000, peak_share=0.5, calendar_years=calendar(),
        launch_year=2027, conversions=conversions(), **BASE_CURVE,
    )
    adjusted = me.apply_probability_of_success(result.patients, 0.6)
    for raw, risked in zip(result.patients, adjusted):
        assert risked == pytest.approx(raw * 0.6)
