import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
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


@pytest.fixture
def seed_reference_product(client):
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["1 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"1 mg": ["3 mL", 3.0]}, presentations_ref="pref",
    ))
    db.commit()
    db.close()


@pytest.fixture
def seed_service_pricing(client):
    from app.models import ServicePricing
    db = next(app.dependency_overrides[get_db]())
    db.add(ServicePricing(key="PKG", payload={"minor": 200, "moderate": 250, "major": 350}))
    db.add(ServicePricing(key="ADD_DV", payload={"value": 50}))
    db.add(ServicePricing(key="TIMELINE", payload={"minor": 3, "moderate": 6, "major": 9}))
    db.add(ServicePricing(key="SERVICES",
                           payload={"standard_dv": 200, "threshold": 2110, "ifu": 1110, "human_factor": 400000}))
    db.commit()
    db.close()


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _assigned_request(client, seed_reference_product, seed_service_pricing):
    """Create, complete, and submit a customer request, then assign it to a KAM.

    Returns (request_id, customer_token, kam_token, kam_user, mgr_token).
    """
    customer_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers=_auth(customer_token)).json()
    request_id = created["id"]
    client.post(f"/requests/{request_id}/select-option", json={"chosen_option": 1}, headers=_auth(customer_token))
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{request_id}/services", headers=_auth(customer_token),
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    client.post(f"/requests/{request_id}/submit", headers=_auth(customer_token))

    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    client.post(f"/requests/{request_id}/assign-kam", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token))

    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_kam_assessment_requires_assigned_kam(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, _ = _assigned_request(client, seed_reference_product, seed_service_pricing)
    other_kam_token, _ = _login(client, "other@shaily.com", name="Other KAM", role="Key Account Manager")

    resp = client.post(f"/requests/{request_id}/kam-assessment",
                        json={"kam_cost_usd": 125000, "kam_timeline_months": 6}, headers=_auth(other_kam_token))
    assert resp.status_code == 404


def test_kam_assessment_sets_fields_and_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assigned_request(client, seed_reference_product, seed_service_pricing)

    resp = client.post(f"/requests/{request_id}/kam-assessment",
                        json={"kam_cost_usd": 125000, "kam_timeline_months": 6, "kam_notes": "New tool required."},
                        headers=_auth(kam_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "KAM Assessment Submitted"
    assert body["kam_cost_usd"] == 125000
    assert body["kam_timeline_months"] == 6
    assert body["kam_notes"] == "New tool required."


def test_kam_assessment_409_before_kam_assigned(client, seed_reference_product, seed_service_pricing):
    customer_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers=_auth(customer_token)).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1}, headers=_auth(customer_token))
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers=_auth(customer_token),
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    client.post(f"/requests/{created['id']}/submit", headers=_auth(customer_token))

    kam_token, kam_user = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.post(f"/requests/{created['id']}/kam-assessment",
                        json={"kam_cost_usd": 100, "kam_timeline_months": 3}, headers=_auth(kam_token))
    assert resp.status_code == 404  # not assigned to this KAM yet
