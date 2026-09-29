import datetime as dt
from pathlib import Path
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.forecasting_engine.api.routes import get_cms_adapter
from app.forecasting_engine.core.units import SourceKind, SourceMetric
from app.forecasting_engine.services.source_cache import SOURCE_SEARCH_CACHE
from app.forecasting_engine.services.sources.base import Observation, SourceSearchResult
from app.main import app


class FakeAdapter:
    """Stands in for CmsPartDAdapter so no test ever touches the network."""

    source_kind = SourceKind.CMS_PART_D

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def search(self, *, molecule, brand, geography, period):
        self.calls += 1
        return self.result


def _observation(**overrides):
    base = dict(
        source_kind=SourceKind.CMS_PART_D, geography="US",
        coverage="Medicare Part D enrolled beneficiaries only. Not total US market volume.",
        period_label="2022", metric=SourceMetric.DOSAGE_UNITS, unit="dosage_units",
        value=Decimal("1234567"), retrieved_at=dt.datetime.now(dt.timezone.utc),
        transformation="none — value as published by CMS", molecule="semaglutide",
        source_url="https://data.cms.gov/data-api/v1/dataset/example/data",
    )
    base.update(overrides)
    return Observation(**base)


@pytest.fixture
def adapter_result():
    return SourceSearchResult(source_kind=SourceKind.CMS_PART_D, available=True,
                              observations=[_observation()])


@pytest.fixture
def fake_adapter(adapter_result):
    return FakeAdapter(adapter_result)


@pytest.fixture
def client(fake_adapter):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_cms_adapter] = lambda: fake_adapter
    SOURCE_SEARCH_CACHE.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()
    SOURCE_SEARCH_CACHE.clear()


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    else:
        body["title"] = "R&D Manager"
        body["phone"] = "+1-555-0100"
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def _make_request(client, token, brand="Ozempic", market="US"):
    resp = client.post("/requests", json={"brand": brand, "market": market}, headers=_headers(token))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


EPI_PARAMS = {
    "molecule": "semaglutide",
    "geography": "US",
    "indication": "Type 2 diabetes",
    "forecast_start_year": 2027,
    "launch_year": 2027,
    "forecast_mode": "epidemiology",
    "target_population": 2_000_000,
    "population_basis": "prevalence",
    "treatment_basis": "chronic",
    "base_peak_share": 0.08,
    "upside_peak_share": 0.15,
    "ramp_speed": 0.8,
    "inflection_year": 4.0,
    "units_per_patient_per_year": 52,
    "units_per_patient_basis": "one weekly injection, 52 weeks of chronic therapy",
    "units_per_pack": 4,
    "active_ingredient_mg_per_unit": 1.34,
    "company_capture_share": 0.35,
}

OBSERVED_PARAMS = {
    "molecule": "semaglutide",
    "geography": "US",
    "forecast_start_year": 2027,
    "launch_year": 2028,
    "forecast_mode": "observed_volume",
    "reference_units": 5_000_000,
    "reference_year": 2024,
    "annual_growth_rate": 0.07,
    "reference_coverage_note": "Medicare Part D only",
    "base_peak_share": 0.05,
    "upside_peak_share": 0.12,
    "ramp_speed": 0.9,
    "inflection_year": 3.5,
    "units_per_pack": 4,
}


def _upsert(client, token, request_id, params, revision=0, expect=200):
    resp = client.post("/forecast/upsert", headers=_headers(token), json={
        "request_id": request_id, "revision": revision, "parameters": params})
    assert resp.status_code == expect, resp.text
    return resp


# --- reading and shape -------------------------------------------------------

def test_get_forecast_for_a_request_with_no_parameters_is_empty_not_an_error(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.get(f"/forecast/{request_id}", headers=_headers(token))
    assert resp.status_code == 200
    assert resp.json()["granularity"] == "none"
    assert resp.json()["forecasts"] == []


def test_upsert_then_get_returns_ten_values_per_metric(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS)

    body = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()
    assert body["granularity"] == "request"
    forecast = body["forecasts"][0]
    assert forecast["deal_id"] == request_id
    assert forecast["revision"] == 1
    assert forecast["model_version"] == "1.0.0"
    assert len(forecast["calendar_years"]) == 10
    assert forecast["calendar_years"][0] == 2027
    for scenario in ("base_case", "upside_case"):
        for metric in ("patients", "business_dosage_units", "business_packs", "business_api_kg"):
            assert len(forecast[scenario][metric]) == 10


def test_upside_is_never_below_base_in_the_response(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS)
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    for base, upside in zip(forecast["base_case"]["patients"], forecast["upside_case"]["patients"]):
        assert upside >= base


def test_calendar_years_align_and_prelaunch_years_are_zero(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, OBSERVED_PARAMS)  # starts 2027, launches 2028
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert forecast["calendar_years"] == list(range(2027, 2037))
    assert forecast["base_case"]["business_dosage_units"][0] == 0.0  # 2027 precedes launch
    assert forecast["base_case"]["business_dosage_units"][1] > 0.0
    # The market itself exists before our launch, so addressable volume is not zeroed.
    assert forecast["base_case"]["addressable_dosage_units"][0] > 0.0


def test_metrics_without_conversion_inputs_are_null_not_zero(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    params = {k: v for k, v in EPI_PARAMS.items()
              if k not in ("units_per_pack", "active_ingredient_mg_per_unit")}
    _upsert(client, token, request_id, params)
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert forecast["base_case"]["business_packs"] is None
    assert forecast["base_case"]["business_api_kg"] is None
    assert forecast["base_case"]["business_dosage_units"] is not None


def test_observed_mode_reports_no_patient_series_and_flags_coverage(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, OBSERVED_PARAMS)
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert forecast["base_case"]["patients"] is None
    assert any("coverage" in w.lower() for w in forecast["warnings"])


def test_revenue_requires_the_full_price_triplet_and_uses_decimal(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    priced = dict(EPI_PARAMS, net_price="12.50", price_currency="USD", price_basis="per_pack")
    _upsert(client, token, request_id, priced)
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    revenue = forecast["base_case"]["business_revenue"]
    assert len(revenue) == 10
    assert float(revenue[5]) == pytest.approx(forecast["base_case"]["business_packs"][5] * 12.5)
    assert forecast["unit_metadata"]["revenue"] == "USD per year at per_pack"


def test_probability_of_success_is_returned_separately(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, dict(EPI_PARAMS, probability_of_success=0.6))
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    raw = forecast["base_case"]["business_dosage_units"]
    risked = forecast["base_case"]["risk_adjusted_business_dosage_units"]
    assert risked is not None
    for r, a in zip(raw, risked):
        assert a == pytest.approx(r * 0.6)


# --- validation --------------------------------------------------------------

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected_by_the_schema(bad):
    """Checked at the schema, which is where the guarantee lives. Literal NaN/Infinity
    are not valid JSON, so no conforming client can send them over the wire."""
    from pydantic import ValidationError

    from app.forecasting_engine.api.schemas import ForecastParametersIn
    with pytest.raises(ValidationError):
        ForecastParametersIn(**dict(EPI_PARAMS, ramp_speed=bad))


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_numbers_sent_as_strings_are_rejected_over_http(client, bad):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, dict(EPI_PARAMS, ramp_speed=bad), expect=422)


def test_unknown_fields_are_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, dict(EPI_PARAMS, sneaky_field=1), expect=422)


def test_base_share_above_upside_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id,
            dict(EPI_PARAMS, base_peak_share=0.9, upside_peak_share=0.1), expect=422)


@pytest.mark.parametrize("field,value", [
    ("ramp_speed", 0), ("ramp_speed", -1), ("units_per_pack", 0),
    ("target_population", -5), ("inflection_year", 0.1), ("inflection_year", 99),
    ("company_capture_share", 1.5),
])
def test_out_of_range_inputs_are_rejected(client, field, value):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, dict(EPI_PARAMS, **{field: value}), expect=422)


def test_epidemiology_mode_requires_population_basis_and_treatment_basis(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    params = {k: v for k, v in EPI_PARAMS.items() if k != "population_basis"}
    _upsert(client, token, request_id, params, expect=422)


def test_observed_mode_rejects_a_patient_population(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id,
            dict(OBSERVED_PARAMS, target_population=1_000_000), expect=422)


def test_observed_mode_rejects_a_second_capture_factor(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id,
            dict(OBSERVED_PARAMS, company_capture_share=0.3), expect=422)


def test_price_without_currency_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, dict(EPI_PARAMS, net_price="10"), expect=422)


def test_override_without_a_reason_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id,
            dict(EPI_PARAMS, overridden_source_value=123.0), expect=422)


# --- access isolation --------------------------------------------------------

def test_forecast_is_not_readable_across_organizations(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    _upsert(client, owner, request_id, EPI_PARAMS)

    assert client.get(f"/forecast/{request_id}", headers=_headers(outsider)).status_code == 404


def test_forecast_is_not_writable_across_organizations(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    _upsert(client, outsider, request_id, EPI_PARAMS, expect=404)


def test_unauthenticated_access_is_rejected(client):
    assert client.get("/forecast/1").status_code == 401
    assert client.get("/forecast/sources/search", params={"request_id": 1, "geography": "US",
                                                          "molecule": "x"}).status_code == 401


def test_source_search_is_not_readable_across_organizations(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    resp = client.get("/forecast/sources/search", headers=_headers(outsider),
                      params={"request_id": request_id, "geography": "US", "molecule": "semaglutide"})
    assert resp.status_code == 404


# --- concurrency -------------------------------------------------------------

def test_second_write_against_a_stale_revision_is_rejected_with_409(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS, revision=0)

    # Two editors both loaded revision 1. The first wins.
    _upsert(client, token, request_id, dict(EPI_PARAMS, base_peak_share=0.09), revision=1)
    resp = _upsert(client, token, request_id, dict(EPI_PARAMS, base_peak_share=0.12),
                   revision=1, expect=409)
    assert "updated by someone else" in resp.json()["detail"]

    # The winner's value survived; the loser's edit was not silently applied.
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert forecast["revision"] == 2
    assert forecast["assumption_summary"]["base_peak_share"] == 0.09


def test_creating_twice_with_revision_zero_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS, revision=0)
    _upsert(client, token, request_id, EPI_PARAMS, revision=0, expect=409)


def test_each_accepted_revision_is_recorded_in_the_audit_history(client):
    from app.forecasting_engine.models.db_models import MoleculeForecastAudit
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS, revision=0)
    _upsert(client, token, request_id, dict(EPI_PARAMS, base_peak_share=0.09), revision=1)

    db = next(app.dependency_overrides[get_db]())
    rows = db.query(MoleculeForecastAudit).order_by(MoleculeForecastAudit.revision).all()
    assert [r.revision for r in rows] == [1, 2]
    assert rows[0].payload["base_peak_share"] == 0.08
    assert rows[1].payload["base_peak_share"] == 0.09
    db.close()


# --- granularity / double counting ------------------------------------------

def _add_sku_row(client, token, request_id, strength="1 mg"):
    client.put(f"/requests/{request_id}", headers=_headers(token), json={
        "brand": "Ozempic", "market": "US", "strengths": [strength], "viscosity_val": None,
        "device": None, "differentiated": False,
        "sku_rows": [{"strength": strength, "cartridge": "3 mL", "fill_ml": 3.0}]})
    detail = client.get(f"/requests/{request_id}", headers=_headers(token)).json()
    return detail["sku_rows"][0]["id"]


def test_sku_level_and_request_level_forecasts_cannot_coexist(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    sku_row_id = _add_sku_row(client, token, request_id)
    _upsert(client, token, request_id, EPI_PARAMS, revision=0)
    # Adding a SKU-level set on top would double-count the same volume.
    resp = client.post("/forecast/upsert", headers=_headers(token), json={
        "request_id": request_id, "revision": 0,
        "parameters": dict(EPI_PARAMS, sku_row_id=sku_row_id)})
    assert resp.status_code == 422
    assert "twice" in resp.json()["detail"]


def test_per_sku_forecasts_are_returned_together_at_sku_granularity(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    sku_row_id = _add_sku_row(client, token, request_id)
    _upsert(client, token, request_id, dict(EPI_PARAMS, sku_row_id=sku_row_id), revision=0)
    body = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()
    assert body["granularity"] == "sku"
    assert body["forecasts"][0]["sku_row_id"] == sku_row_id
    # And a request-level set may not then be added alongside it.
    resp = client.post("/forecast/upsert", headers=_headers(token), json={
        "request_id": request_id, "revision": 0, "parameters": EPI_PARAMS})
    assert resp.status_code == 422


def test_a_sku_row_from_another_request_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    first = _make_request(client, token)
    client.put(f"/requests/{first}", headers=_headers(token), json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg"], "viscosity_val": None,
        "device": None, "differentiated": False,
        "sku_rows": [{"strength": "1 mg", "cartridge": "3 mL", "fill_ml": 3.0}]})
    second = _make_request(client, token, brand="Trulicity")

    detail = client.get(f"/requests/{first}", headers=_headers(token)).json()
    foreign_sku_id = detail["sku_rows"][0]["id"]
    resp = client.post("/forecast/upsert", headers=_headers(token), json={
        "request_id": second, "revision": 0,
        "parameters": dict(EPI_PARAMS, sku_row_id=foreign_sku_id)})
    assert resp.status_code == 422


# --- sources -----------------------------------------------------------------

def test_source_search_returns_observations_with_coverage_and_provenance(client, fake_adapter):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.get("/forecast/sources/search", headers=_headers(token),
                      params={"request_id": request_id, "geography": "US", "molecule": "semaglutide"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    row = body["results"][0]
    assert "Not total US market" in row["coverage"]
    assert row["source_url"].startswith("https://data.cms.gov/")
    assert row["metric"] == "dosage_units"


def test_source_search_does_not_modify_saved_parameters(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _upsert(client, token, request_id, EPI_PARAMS)
    before = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()
    client.get("/forecast/sources/search", headers=_headers(token),
               params={"request_id": request_id, "geography": "US", "molecule": "semaglutide"})
    after = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()
    assert before == after


def test_repeated_searches_are_served_from_the_bounded_cache(client, fake_adapter):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    params = {"request_id": request_id, "geography": "US", "molecule": "semaglutide"}
    client.get("/forecast/sources/search", headers=_headers(token), params=params)
    client.get("/forecast/sources/search", headers=_headers(token), params=params)
    assert fake_adapter.calls == 1


def test_an_upsert_supersedes_cached_source_results(client, fake_adapter):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    params = {"request_id": request_id, "geography": "US", "molecule": "semaglutide"}
    client.get("/forecast/sources/search", headers=_headers(token), params=params)
    _upsert(client, token, request_id, EPI_PARAMS)
    client.get("/forecast/sources/search", headers=_headers(token), params=params)
    assert fake_adapter.calls == 2


def test_an_unavailable_source_reports_why_instead_of_returning_nothing(client, fake_adapter):
    fake_adapter.result = SourceSearchResult(
        source_kind=SourceKind.CMS_PART_D, available=False,
        unavailable_reason="CMS dataset descriptor is not verified.")
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.get("/forecast/sources/search", headers=_headers(token),
                      params={"request_id": request_id, "geography": "US", "molecule": "semaglutide"})
    body = resp.json()
    assert body["available"] is False
    assert "not verified" in body["unavailable_reason"]
    assert body["results"] == []


def test_a_search_without_a_molecule_or_brand_is_rejected(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.get("/forecast/sources/search", headers=_headers(token),
                      params={"request_id": request_id, "geography": "US"})
    assert resp.status_code == 422


def test_csv_import_stores_rows_with_provenance_and_keeps_blanks_null(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    csv_payload = (
        "geography,coverage,period_label,metric,unit,value,molecule,source_url\n"
        "EU,IQVIA MIDAS licensed extract,2024,dosage_units,dosage_units,900000,semaglutide,https://example.org/a\n"
        "EU,IQVIA MIDAS licensed extract,2024,dosage_units,dosage_units,,semaglutide,https://example.org/b\n"
    )
    resp = client.post("/forecast/sources/import", headers=_headers(token), json={
        "request_id": request_id, "format": "csv", "payload": csv_payload})
    assert resp.status_code == 200, resp.text
    rows = resp.json()["results"]
    assert len(rows) == 2
    assert rows[0]["value"] == "900000.0000"
    assert rows[1]["value"] is None  # suppressed stays null, never 0
    assert rows[0]["source_kind"] == "file_import"


def test_csv_import_reports_bad_rows_without_discarding_good_ones(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    csv_payload = (
        "geography,coverage,period_label,metric,unit,value\n"
        "EU,licensed extract,2024,dosage_units,dosage_units,100\n"
        "EU,licensed extract,2024,not_a_metric,dosage_units,100\n"
        "EU,licensed extract,2024,spending,currency,100\n"
    )
    resp = client.post("/forecast/sources/import", headers=_headers(token), json={
        "request_id": request_id, "format": "csv", "payload": csv_payload})
    body = resp.json()
    assert len(body["results"]) == 1
    assert any("not_a_metric" in w for w in body["warnings"])
    assert any("currency" in w for w in body["warnings"])


def test_import_is_not_permitted_across_organizations(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    resp = client.post("/forecast/sources/import", headers=_headers(outsider), json={
        "request_id": request_id, "format": "json",
        "rows": [{"geography": "EU", "coverage": "x", "period_label": "2024",
                  "metric": "dosage_units", "unit": "dosage_units", "value": "1"}]})
    assert resp.status_code == 404


# --- non-finite JSON literals (regression) -----------------------------------

@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_a_bare_non_finite_json_literal_returns_422_not_500(client, literal):
    """Regression: FastAPI echoes the offending input into its 422 body, and Starlette
    serialises with allow_nan=False, so a bare NaN/Infinity literal used to make the
    error response itself fail to encode and surface as a 500."""
    import json as jsonlib

    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    payload = {"request_id": request_id, "revision": 0,
               "parameters": dict(EPI_PARAMS, ramp_speed=float(literal))}
    resp = client.post(
        "/forecast/upsert",
        headers={**_headers(token), "Content-Type": "application/json"},
        content=jsonlib.dumps(payload, allow_nan=True).encode(),
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("literal", ["NaN", "Infinity"])
def test_the_422_body_keeps_the_frontend_error_contract(client, literal):
    """frontend/lib/api.ts parseError expects a 422 whose detail is a list of items
    carrying loc and msg; it builds per-field errors from those."""
    import json as jsonlib

    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    payload = {"request_id": request_id, "revision": 0,
               "parameters": dict(EPI_PARAMS, ramp_speed=float(literal))}
    resp = client.post(
        "/forecast/upsert",
        headers={**_headers(token), "Content-Type": "application/json"},
        content=jsonlib.dumps(payload, allow_nan=True).encode(),
    )
    body = resp.json()
    assert isinstance(body["detail"], list) and body["detail"]
    item = body["detail"][0]
    assert isinstance(item["loc"], list) and isinstance(item["msg"], str)
    assert item["loc"][-1] == "ramp_speed"
    # The echoed input is rendered as a string rather than an invalid JSON literal.
    assert resp.text.count("NaN") == 0 or isinstance(item.get("input"), str)


def test_an_ordinary_validation_error_is_unchanged_by_the_handler(client):
    """The handler must not alter the normal case for any existing router."""
    resp = client.post("/auth/login", json={"name": "x", "email": "not-an-email"})
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], list)
    assert "loc" in body["detail"][0] and "msg" in body["detail"][0]


# --- CMS official-download ingestion ----------------------------------------

CMS_FIXTURE = Path(__file__).parent / "fixtures" / "cms_part_d_dy2024_excerpt.csv"


def test_ingesting_the_official_cms_file_stores_observations_with_provenance(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": CMS_FIXTURE.read_text(encoding="utf-8-sig"),
        "brand": "Ozempic", "data_year": 2024,
        "retrieval_note": "official CMS CSV download, obtained out of band"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "available"
    dosage = [r for r in body["results"] if r["metric"] == "dosage_units"]
    assert len(dosage) == 1
    assert dosage[0]["value"] == "42324232.8360"
    assert dosage[0]["source_url"].endswith("DSD_PTD_RY26_P04_V10_DY24_BGM.csv")
    assert dosage[0]["period_label"] == "2024"
    assert "Not total US market volume" in dosage[0]["coverage"]


def test_cms_ingest_reports_no_matching_records_distinctly(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": CMS_FIXTURE.read_text(encoding="utf-8-sig"),
        "brand": "NoSuchDrug", "data_year": 2024})
    body = resp.json()
    assert body["status"] == "no_matching_records"
    assert body["results"] == []


def test_cms_ingest_reports_configuration_incomplete_for_an_unusable_file(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": "a,b,c\n1,2,3\n", "brand": "Ozempic"})
    assert resp.json()["status"] == "configuration_incomplete"


def test_cms_ingest_requires_a_molecule_or_brand(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": "x", "data_year": 2024})
    assert resp.status_code == 422


def test_cms_ingest_is_not_permitted_across_organizations(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    resp = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(outsider), json={
        "request_id": request_id, "payload": CMS_FIXTURE.read_text(encoding="utf-8-sig"),
        "brand": "Ozempic", "data_year": 2024})
    assert resp.status_code == 404


def test_an_ingested_cms_figure_can_back_an_observed_volume_forecast(client):
    """End to end: official CMS dosage units become the observed-volume baseline, and the
    saved forecast cites the observation it came from."""
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    ingest = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": CMS_FIXTURE.read_text(encoding="utf-8-sig"),
        "brand": "Ozempic", "data_year": 2024}).json()
    dosage = next(r for r in ingest["results"] if r["metric"] == "dosage_units")

    params = dict(OBSERVED_PARAMS,
                  reference_units=int(float(dosage["value"])),
                  reference_year=2024,
                  reference_coverage_note=dosage["coverage"],
                  source_observation_id=dosage["id"])
    _upsert(client, token, request_id, params)

    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert forecast["source_references"][0]["id"] == dosage["id"]
    assert forecast["source_references"][0]["source_url"].endswith(
        "DSD_PTD_RY26_P04_V10_DY24_BGM.csv")
    assert forecast["base_case"]["addressable_dosage_units"][0] > 0
    assert any("coverage" in w.lower() for w in forecast["warnings"])


# --- CMS source status: three independent facts ------------------------------

def _ingest_cms(client, token, request_id, archived=True):
    body = {"request_id": request_id,
            "payload": CMS_FIXTURE.read_text(encoding="utf-8-sig"),
            "brand": "Ozempic", "data_year": 2024}
    if archived:
        body["retrieval_url"] = (
            "https://web.archive.org/web/20260923112137id_/https://data.cms.gov/sites/default/"
            "files/2026-06/98218f98-166c-4723-8438-c344a4ef96a6/DSD_PTD_RY26_P04_V10_DY24_BGM.csv")
        body["archive_capture_date"] = "2026-09-23T11:21:37Z"
        body["retrieval_note"] = "archived CMS publication via Internet Archive"
    return client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json=body)


def test_an_archived_ingest_records_both_urls_and_the_checksum(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    row = next(r for r in _ingest_cms(client, token, request_id).json()["results"]
               if r["metric"] == "dosage_units")
    assert row["provenance_class"] == "archived_cms_publication"
    assert row["source_url"].startswith("https://data.cms.gov/")          # publication URL
    assert row["retrieval_url"].startswith("https://web.archive.org/")     # retrieval URL
    assert row["archive_capture_date"].startswith("2026-09-23T11:21:37")
    assert len(row["content_sha256"]) == 64


def test_status_reports_reporting_year_and_last_successful_refresh(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["reporting_year"] == 2024
    assert body["latest_published_year"] == 2024
    # No metadata check has run, so freshness is unknown rather than assumed current.
    assert body["publication_freshness"] == "unknown"
    assert "not current-year sales" in body["freshness_label"]
    assert body["last_successful_refresh"] is not None
    assert body["last_refresh_provenance"] == "archived_cms_publication"
    assert body["retrieval_url"].startswith("https://web.archive.org/")
    assert body["observation_count"] == 4


def test_the_three_statuses_are_reported_independently(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    # A usable file, an unconfirmed publication year and an unchecked API coexist:
    # none of the three implies either of the others.
    assert body["file_verification"] == "unrecognised"
    assert body["publication_freshness"] == "unknown"
    assert body["api_connectivity"] == "not_checked"


def test_status_does_not_touch_the_network_unless_asked(client, monkeypatch):
    from app.forecasting_engine.services.sources import cms_part_d

    def explode(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("status must not probe the API unless check_api is set")

    monkeypatch.setattr(cms_part_d, "probe_api", explode)
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id})
    assert resp.status_code == 200
    assert resp.json()["api_connectivity"] == "not_checked"


def test_status_with_no_ingest_yet_still_answers(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["reporting_year"] is None
    assert body["last_successful_refresh"] is None
    assert body["publication_freshness"] == "unknown"
    assert body["latest_published_year"] == 2024


def test_status_is_org_isolated(client):
    owner = _login(client, "anaya@pfizer.com")
    outsider = _login(client, "someone@othercompany.com")
    request_id = _make_request(client, owner)
    resp = client.get("/forecast/sources/cms-part-d/status", headers=_headers(outsider),
                      params={"request_id": request_id})
    assert resp.status_code == 404


def test_a_blocked_probe_surfaces_the_support_summary(client, monkeypatch):
    import datetime as dt

    from app.forecasting_engine.core.units import ApiConnectivity
    from app.forecasting_engine.services.sources import cms_part_d

    report = cms_part_d.ConnectivityReport(
        status=ApiConnectivity.BLOCKED,
        endpoint="https://data.cms.gov/data-api/v1/dataset/x/data",
        checked_at=dt.datetime(2026, 9, 29, 9, 6, 19, tzinfo=dt.timezone.utc),
        http_status=403, akamai_reference="18.65c90b17.1790672781.a9b10530",
        detail="Denied at the edge.")
    monkeypatch.setattr(cms_part_d, "probe_api", lambda *a, **k: report)

    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id, "check_api": True}).json()
    assert body["api_connectivity"] == "blocked"
    assert body["akamai_reference"] == "18.65c90b17.1790672781.a9b10530"
    assert "403" in body["support_summary"]
    # The file stays usable regardless of connectivity.
    assert body["reporting_year"] == 2024
    assert body["last_successful_refresh"] is not None


def test_the_application_stays_usable_on_imported_data_while_the_api_is_blocked(client):
    """No live connectivity anywhere in this flow: ingest, forecast, read back."""
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    dosage = next(r for r in _ingest_cms(client, token, request_id).json()["results"]
                  if r["metric"] == "dosage_units")
    _upsert(client, token, request_id, dict(
        OBSERVED_PARAMS, reference_units=int(float(dosage["value"])), reference_year=2024,
        source_observation_id=dosage["id"]))
    forecast = client.get(f"/forecast/{request_id}", headers=_headers(token)).json()["forecasts"][0]
    assert len(forecast["base_case"]["business_dosage_units"]) == 10
    assert forecast["source_references"][0]["provenance_class"] == "archived_cms_publication"


# --- release registry and freshness ------------------------------------------

def _record_metadata_check(client, *, status="ok", latest_year=2024, days_ago=0,
                           new_release=False, detail="check"):
    """Insert a metadata-check row directly, standing in for the scheduled command."""
    import datetime as dt

    from app.forecasting_engine.models.db_models import CmsMetadataCheck
    db = next(app.dependency_overrides[get_db]())
    db.add(CmsMetadataCheck(
        source_kind="cms_part_d",
        checked_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago),
        status=status, latest_data_year_seen=latest_year, new_release_detected=new_release,
        detail=detail, metadata_url="https://datahub.hhs.gov/api/views/xzs3-ddeh.json"))
    db.commit()
    db.close()


def test_freshness_is_current_only_after_a_recent_successful_metadata_check(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    _record_metadata_check(client, latest_year=2024, days_ago=1)

    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["publication_freshness"] == "current"
    assert body["freshness_label"].startswith("Latest published: 2024")
    assert "not current-year sales" in body["freshness_label"]
    assert body["last_metadata_check_status"] == "ok"
    assert body["last_metadata_check_at"] is not None


def test_a_stale_metadata_check_degrades_freshness_to_unknown(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    _record_metadata_check(client, latest_year=2024, days_ago=120)

    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["publication_freshness"] == "unknown"
    assert "not confirmed" in body["freshness_label"]


def test_an_unreachable_metadata_check_does_not_make_the_data_current(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    _record_metadata_check(client, status="unreachable", latest_year=None, days_ago=0)

    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["publication_freshness"] == "unknown"
    assert body["last_metadata_check_status"] == "unreachable"


def test_a_newer_published_year_marks_the_loaded_year_superseded(client):
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)
    _record_metadata_check(client, latest_year=2025, days_ago=1, new_release=True,
                           detail="CMS now publishes reporting year 2025")

    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["publication_freshness"] == "superseded"
    assert body["new_release_detected"] is True
    assert "2025" in body["freshness_label"] and "2024" in body["freshness_label"]


def test_an_ingested_file_is_validated_and_promoted_without_a_digest_edit(client):
    """A file whose checksum is unknown to the descriptor still validates on its merits."""
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    resp = _ingest_cms(client, token, request_id)
    assert any("Release validated and promoted" in w for w in resp.json()["warnings"])

    body = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                      params={"request_id": request_id}).json()
    assert body["active_release_status"] == "validated"
    assert body["active_release_validated_at"] is not None
    names = {c["name"] for c in body["active_release_checks"]}
    assert names == {"provenance", "schema", "units", "duplicates"}
    assert all(c["passed"] for c in body["active_release_checks"])


def test_a_file_with_no_rollup_rows_yields_nothing_and_promotes_nothing(client):
    """Without the 'Overall' roll-up, brand totals cannot be de-duplicated, so the file
    produces no observations and nothing reaches the active release slot."""
    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    lines = CMS_FIXTURE.read_text(encoding="utf-8-sig").splitlines()
    manufacturer_row = next(l for l in lines[1:]
                            if l.startswith("Ozempic,") and "Novo Nordisk" in l)
    body = client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": lines[0] + "\n" + manufacturer_row + "\n",
        "brand": "Ozempic", "data_year": 2024}).json()
    assert body["status"] == "no_matching_records"
    assert body["results"] == []

    status = client.get("/forecast/sources/cms-part-d/status", headers=_headers(token),
                        params={"request_id": request_id}).json()
    assert status["active_release_status"] is None


def test_promoting_a_new_release_preserves_the_previous_one(client):
    from app.forecasting_engine.models.db_models import CmsDatasetRelease
    from app.forecasting_engine.services.sources import cms_release_registry

    token = _login(client, "anaya@pfizer.com")
    request_id = _make_request(client, token)
    _ingest_cms(client, token, request_id)

    # A second, different file for a later reporting year.
    text = CMS_FIXTURE.read_text(encoding="utf-8-sig").replace("_2024", "_2025")
    client.post("/forecast/sources/cms-part-d/ingest", headers=_headers(token), json={
        "request_id": request_id, "payload": text, "brand": "Ozempic", "data_year": 2025})

    db = next(app.dependency_overrides[get_db]())
    rows = db.query(CmsDatasetRelease).order_by(CmsDatasetRelease.id).all()
    assert len(rows) == 2
    assert rows[0].validation_status == cms_release_registry.SUPERSEDED
    assert rows[0].is_active is False       # preserved, not deleted
    assert rows[1].is_active is True
    assert rows[0].content_sha256 != rows[1].content_sha256
    db.close()
