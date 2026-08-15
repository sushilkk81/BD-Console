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


def test_login_internal_requires_role(client):
    resp = client.post("/auth/login", json={"name": "Mahesh", "email": "mahesh@shaily.com"})
    assert resp.status_code == 422


def test_login_internal_ok(client):
    resp = client.post("/auth/login", json={
        "name": "Mahesh", "email": "mahesh@shaily.com", "role": "BD Manager"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "BD Manager"
    assert body["access_token"]


def test_login_customer_creates_org_by_domain(client):
    resp = client.post("/auth/login", json={"name": "Dr. Mehta", "email": "anaya@pfizer.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "Customer"
