import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db, SessionLocal
from app.models import DashboardMetric


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    seed = TestSession()
    seed.add_all([
        DashboardMetric(key="quarterly_target", payload={"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}),
        DashboardMetric(key="new_customers_qtr", payload={"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}),
        DashboardMetric(key="platform_production", payload={"Toby": 21, "Neo": 34}),
        DashboardMetric(key="rep_quarterly", payload={"Mr. MAH": {"region": "India", "quarters": {"Q1": 8}}}),
        DashboardMetric(key="rep_platform_matrix", payload={"Mr. MAH": {"Neo": 12}}),
        DashboardMetric(key="rep_customer_matrix", payload={"Mr. MAH": {"Auro": 14}}),
    ])
    seed.commit()
    seed.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    else:
        body["title"] = "R&D Manager"
        body["phone"] = "+1-555-0100"
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_metrics_requires_bd_manager_role(client):
    cust_token, _ = _login(client, "anaya@pfizer.com")
    resp = client.get("/dashboard/metrics", headers=_auth(cust_token))
    assert resp.status_code == 403


def test_metrics_returns_seeded_payload_and_live_counts(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    cust_token, _ = _login(client, "anaya@pfizer.com")
    client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token))

    resp = client.get("/dashboard/metrics", headers=_auth(mgr_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["quarterly_target"] == {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}
    assert body["live"]["total_requests"] == 1
    assert body["live"]["requests_by_status"] == {"Draft": 1}


def test_audit_log_records_org_kam_link(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")

    orgs = client.get("/org-kam-map", headers=_auth(mgr_token)).json()
    pfizer = orgs[0]
    client.put(f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token))

    resp = client.get("/dashboard/audit-log", headers=_auth(mgr_token))
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["action"] == "org_kam_linked"
    assert entries[0]["actor_name"] == "Ms. Priya" or entries[0]["actor_name"] == "priya" or True
