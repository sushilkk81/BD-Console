import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db
from app.services.external_lookup import (
    LookupService,
    StrengthLookupResult,
    ViscosityLookupResult,
    get_lookup_service,
)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class FakeLookupService(LookupService):
    def __init__(self, strengths_result=None, viscosity_result=None):
        self._strengths_result = strengths_result or StrengthLookupResult(found=False)
        self._viscosity_result = viscosity_result or ViscosityLookupResult(found=False)

    def lookup_strengths(self, brand, market):
        return self._strengths_result

    def lookup_viscosity(self, brand, molecule):
        return self._viscosity_result


def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100",
    })
    return resp.json()["access_token"]


def test_strengths_lookup_requires_auth(client):
    resp = client.post("/reference-lookup/strengths", json={"brand": "Ozempic", "market": "US"})
    assert resp.status_code == 401


def test_strengths_lookup_miss_returns_found_false(client):
    token = _login(client)
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()
    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "TotallyNewBrand", "market": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_strengths_lookup_hit_creates_new_reference_product_and_market_row(client):
    token = _login(client)
    fake = FakeLookupService(strengths_result=StrengthLookupResult(
        found=True, molecule="Semaglutide", device="Pen Injector",
        strengths=[{"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5}],
        citation="FDA label 209637",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "BrandNewDrug", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["molecule"] == "Semaglutide"
    assert body["strengths"] == [{"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5}]

    # second call for the same brand+market is a cache hit — no external call needed
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()  # would return found=False
    resp2 = client.post(
        "/reference-lookup/strengths", json={"brand": "BrandNewDrug", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.json()["found"] is True
    assert resp2.json()["molecule"] == "Semaglutide"


def test_strengths_lookup_hit_does_not_overwrite_existing_base_row(client, seed_reference_product=None):
    token = _login(client)
    # Seed a base row the way migration 0003 would, via the existing reference-products flow:
    from app.db import get_db
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1.5 mL", 1.5]}, presentations_ref="pref",
    ))
    db.commit()
    db.close()

    fake = FakeLookupService(strengths_result=StrengthLookupResult(
        found=True, molecule="Wrong Molecule Name", device="Wrong Device",
        strengths=[{"strength": "1 mg", "cartridge": "3 mL", "fill_ml": 3.0}],
        citation="South Korea label",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "Ozempic", "market": "South Korea"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "Ozempic")
    assert base.molecule == "Semaglutide"  # untouched by the market-specific lookup
    db.close()


def test_strengths_lookup_cache_hit_returns_persisted_citation(client):
    token = _login(client)
    fake = FakeLookupService(strengths_result=StrengthLookupResult(
        found=True, molecule="Semaglutide", device="Pen Injector",
        strengths=[{"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5}],
        citation="FDA label 209637",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "CitationBrand", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["citation"] == "FDA label 209637"

    # cache hit — citation must survive the round-trip, not come back null
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()
    resp2 = client.post(
        "/reference-lookup/strengths", json={"brand": "CitationBrand", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.json()["found"] is True
    assert resp2.json()["citation"] == "FDA label 209637"


def test_viscosity_lookup_miss_returns_found_false(client):
    token = _login(client)
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()
    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "TotallyNewBrand"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_viscosity_lookup_hit_persists_visc_val(client):
    token = _login(client)
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="AnotherNewDrug", molecule="Somemab", device="Pen Injector", dose="variable", visc="water",
        visc_val=0, cartridge="3 mL", strengths=[], visc_ref="",
        mech_drive="", mech_dose="", mech_label="", ob_ref="", ob_claims=[],
        presentations={}, presentations_ref="",
    ))
    db.commit()
    db.close()

    fake = FakeLookupService(viscosity_result=ViscosityLookupResult(
        found=True, visc_val_low=2.0, visc_val_high=2.3, citations=["DailyMed SmPC"],
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "AnotherNewDrug", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert resp.json()["visc_val_low"] == 2.0
    assert resp.json()["visc_val_high"] == 2.3
    assert resp.json()["citations"] == ["DailyMed SmPC"]

    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "AnotherNewDrug")
    assert float(base.visc_val_low) == 2.0
    assert float(base.visc_val_high) == 2.3
    assert float(base.visc_val) == 2.3  # matching engine gets the conservative (high) end
    db.close()


def test_viscosity_lookup_hit_for_brand_new_to_db_persists_and_caches(client):
    token = _login(client)
    fake = FakeLookupService(viscosity_result=ViscosityLookupResult(
        found=True, visc_val_low=3.5, visc_val_high=4.1,
        citations=["Some literature source", "Second source"],
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "NeverSeenBrand", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert resp.json()["visc_val_low"] == 3.5
    assert resp.json()["visc_val_high"] == 4.1
    assert resp.json()["citations"] == ["Some literature source", "Second source"]

    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "NeverSeenBrand")
    assert base is not None
    assert float(base.visc_val) == 4.1
    assert base.visc_ref == "Some literature source"
    assert base.visc_citations == ["Some literature source", "Second source"]
    db.close()

    # second call must be served from the cache — the fake would raise/return found=False
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()  # found=False if hit
    resp2 = client.post(
        "/reference-lookup/viscosity", json={"brand": "NeverSeenBrand", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.json()["found"] is True
    assert resp2.json()["visc_val_low"] == 3.5
    assert resp2.json()["visc_val_high"] == 4.1


def test_viscosity_lookup_falls_back_to_legacy_single_value_row(client):
    """A ReferenceProduct seeded before this feature (e.g. ported curated data) only has the
    original single visc_val/visc_ref pair — the endpoint must still serve it as a degenerate
    (low == high) range instead of treating it as a cache miss."""
    token = _login(client)
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="CuratedLegacyDrug", molecule="Somemab", device="Pen Injector", dose="variable",
        visc="water", visc_val=1.4, cartridge="3 mL", strengths=[], visc_ref="Original curated ref",
        mech_drive="", mech_dose="", mech_label="", ob_ref="", ob_claims=[],
        presentations={}, presentations_ref="",
    ))
    db.commit()
    db.close()

    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()  # would be found=False
    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "CuratedLegacyDrug", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["visc_val_low"] == 1.4
    assert body["visc_val_high"] == 1.4
    assert body["citations"] == ["Original curated ref"]
