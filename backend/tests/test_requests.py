import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db


@pytest.fixture
def client():
    # StaticPool keeps a single SQLite connection alive across threads, which is
    # required because TestClient dispatches requests on a different thread than
    # the one that created the tables below.
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    resp = client.post("/auth/login", json=body)
    return resp.json()["access_token"], resp.json()["user"]


def test_create_and_list_request(client):
    token, _ = _login(client, "anaya@pfizer.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "Awaiting assignment"

    resp = client.get("/requests", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_requests_are_org_isolated(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.json() == []


def test_requests_requires_auth(client):
    resp = client.get("/requests")
    assert resp.status_code == 401


def test_bd_manager_sees_requests_across_customer_orgs(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})
    client.post("/requests", json={"brand": "Trulicity", "market": "EU"},
                headers={"Authorization": f"Bearer {other_token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {mgr_token}"})
    assert resp.status_code == 200
    brands = {r["brand"] for r in resp.json()}
    assert brands == {"Ozempic", "Trulicity"}
    assert all(r["org_name"] for r in resp.json())


def test_kam_sees_only_requests_assigned_to_them(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    other_kam_token, other_kam = _login(client, "muk@shaily.com", name="Mr. MUK", role="Key Account Manager")

    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {pfizer_token}"}).json()
    client.post(f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]},
                headers={"Authorization": f"Bearer {mgr_token}"})

    mine = client.get("/requests", headers={"Authorization": f"Bearer {kam_token}"}).json()
    assert len(mine) == 1 and mine[0]["brand"] == "Ozempic"

    not_mine = client.get("/requests", headers={"Authorization": f"Bearer {other_kam_token}"}).json()
    assert not_mine == []


def test_customer_request_list_still_org_scoped_with_org_name(client):
    token, _ = _login(client, "anaya@pfizer.com")
    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()[0]["org_name"] == "pfizer.com"
