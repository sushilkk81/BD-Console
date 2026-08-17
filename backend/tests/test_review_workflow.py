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


def _assessed_request(client, seed_reference_product, seed_service_pricing):
    """Extend _assigned_request through a submitted KAM assessment."""
    request_id, customer_token, kam_token, kam_user, mgr_token = _assigned_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/kam-assessment",
                json={"kam_cost_usd": 125000, "kam_timeline_months": 6, "kam_notes": "New tool required."},
                headers=_auth(kam_token))
    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_bd_review_requires_bd_manager_role(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(kam_token))
    assert resp.status_code == 403


def test_bd_review_approve_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, mgr_token = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Approved — Awaiting KAM Response"


def test_bd_review_revise_requires_note_and_posts_internal_message(
    client, seed_reference_product, seed_service_pricing,
):
    request_id, _, kam_token, _, mgr_token = _assessed_request(client, seed_reference_product, seed_service_pricing)

    missing_note = client.post(f"/requests/{request_id}/bd-review", json={"decision": "revise"},
                                headers=_auth(mgr_token))
    assert missing_note.status_code == 422

    resp = client.post(f"/requests/{request_id}/bd-review",
                        json={"decision": "revise", "note": "Please re-check the tool cost."},
                        headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Revision Requested"

    messages = client.get(f"/requests/{request_id}/messages", headers=_auth(kam_token)).json()
    internal = [m for m in messages if m["channel"] == "internal"]
    assert len(internal) == 1
    assert internal[0]["body"] == "Please re-check the tool cost."


def test_bd_review_409_before_assessment_submitted(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, mgr_token = _assigned_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    assert resp.status_code == 409


def _approved_request(client, seed_reference_product, seed_service_pricing):
    """Extend _assessed_request through BD Manager approval."""
    request_id, customer_token, kam_token, kam_user, mgr_token = _assessed_request(
        client, seed_reference_product, seed_service_pricing)
    client.post(f"/requests/{request_id}/bd-review", json={"decision": "approve"}, headers=_auth(mgr_token))
    return request_id, customer_token, kam_token, kam_user, mgr_token


def test_respond_to_customer_requires_assigned_kam(client, seed_reference_product, seed_service_pricing):
    request_id, _, _, _, _ = _approved_request(client, seed_reference_product, seed_service_pricing)
    other_kam_token, _ = _login(client, "other@shaily.com", name="Other KAM", role="Key Account Manager")
    resp = client.post(f"/requests/{request_id}/respond-to-customer", json={"message": "All set."},
                        headers=_auth(other_kam_token))
    assert resp.status_code == 404


def test_respond_to_customer_posts_message_and_advances_status(client, seed_reference_product, seed_service_pricing):
    request_id, customer_token, kam_token, _, _ = _approved_request(
        client, seed_reference_product, seed_service_pricing)

    resp = client.post(f"/requests/{request_id}/respond-to-customer",
                        json={"message": "Approved — cost and timeline attached."}, headers=_auth(kam_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "Responded to Customer"

    messages = client.get(f"/requests/{request_id}/messages", headers=_auth(customer_token)).json()
    assert [m["body"] for m in messages] == ["Approved — cost and timeline attached."]
    assert all(m["channel"] == "customer" for m in messages)


def test_respond_to_customer_409_before_approved(client, seed_reference_product, seed_service_pricing):
    request_id, _, kam_token, _, _ = _assessed_request(client, seed_reference_product, seed_service_pricing)
    resp = client.post(f"/requests/{request_id}/respond-to-customer", json={"message": "hi"},
                        headers=_auth(kam_token))
    assert resp.status_code == 409
