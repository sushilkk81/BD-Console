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


def test_kams_roster_requires_bd_manager_role(client):
    kam_token, _ = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.get("/kams", headers=_auth(kam_token))
    assert resp.status_code == 403


def test_kams_roster_lists_shaily_kams(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "mah@shaily.com", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")  # a customer — must not appear

    resp = client.get("/kams", headers=_auth(mgr_token))
    assert resp.status_code == 200
    names = [k["name"] for k in resp.json()]
    assert names == ["Test User"]  # default _login name


def test_org_kam_map_set_and_list(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    _login(client, "anaya@pfizer.com")  # creates the Pfizer org

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = next(o for o in orgs_resp.json() if o["org_name"] == "pfizer.com")
    assert pfizer["kam_user_id"] is None

    put_resp = client.put(
        f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token),
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["kam_name"] == "Mr. MAH"

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = next(o for o in orgs_resp.json() if o["org_name"] == "pfizer.com")
    assert pfizer["kam_user_id"] == kam_user["id"]


def test_org_kam_map_rejects_non_kam_user(client):
    mgr_token, mgr_user = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    orgs_resp = client.get("/org-kam-map", headers=_auth(mgr_token))
    pfizer = orgs_resp.json()[0]

    resp = client.put(
        f"/org-kam-map/{pfizer['org_id']}", json={"kam_user_id": mgr_user["id"]}, headers=_auth(mgr_token),
    )
    assert resp.status_code == 422


def test_assign_kam_updates_request_status(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    cust_token, _ = _login(client, "anaya@pfizer.com")

    created = client.post(
        "/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token),
    ).json()

    resp = client.post(
        f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]}, headers=_auth(mgr_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assigned_kam_id"] == kam_user["id"]
    assert body["status"] == "Assigned to Mr. MAH"


def test_assign_kam_requires_bd_manager_role(client):
    cust_token, _ = _login(client, "anaya@pfizer.com")
    created = client.post(
        "/requests", json={"brand": "Ozempic", "market": "US"}, headers=_auth(cust_token),
    ).json()

    resp = client.post(
        f"/requests/{created['id']}/assign-kam", json={"kam_user_id": 999}, headers=_auth(cust_token),
    )
    assert resp.status_code == 403
