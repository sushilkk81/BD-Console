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
    return resp.json()["access_token"]


def test_create_and_list_request(client):
    token = _login(client, "anaya@pfizer.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"}, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "Awaiting assignment"

    resp = client.get("/requests", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_requests_are_org_isolated(client):
    pfizer_token = _login(client, "anaya@pfizer.com")
    other_token = _login(client, "someone@othercompany.com")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})

    resp = client.get("/requests", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.json() == []


def test_requests_requires_auth(client):
    resp = client.get("/requests")
    assert resp.status_code == 401
