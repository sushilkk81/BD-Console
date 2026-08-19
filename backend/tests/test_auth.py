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
    resp = client.post("/auth/login", json={
        "name": "Dr. Mehta", "email": "anaya@pfizer.com",
        "title": "R&D Manager", "phone": "+1-555-0100",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "Customer"


def test_login_customer_requires_title_and_phone(client):
    resp = client.post("/auth/login", json={"name": "Dr. Mehta", "email": "anaya@pfizer.com"})
    assert resp.status_code == 422


def test_login_customer_ok_with_title_and_phone(client):
    resp = client.post("/auth/login", json={
        "name": "Dr. Mehta", "email": "anaya@pfizer.com",
        "title": "R&D Manager", "phone": "+1-555-0100",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["role"] == "Customer"
    assert body["session_id"]


def test_login_internal_has_no_session_id(client):
    resp = client.post("/auth/login", json={"name": "Mahesh", "email": "mahesh@shaily.com", "role": "BD Manager"})
    assert resp.json()["session_id"] is None


def test_first_customer_login_notifies_every_bd_manager(client):
    mgr1_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    mgr2_token = client.post("/auth/login", json={
        "name": "Rahul", "email": "rahul@shaily.com", "role": "BD Manager"}).json()["access_token"]

    client.post("/auth/login", json={
        "name": "Dr. Mehta", "email": "anaya@pfizer.com",
        "title": "R&D Manager", "phone": "+1-555-0100",
    })

    for token in (mgr1_token, mgr2_token):
        resp = client.get("/notifications", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert "Dr. Mehta" in resp.json()[0]["message"]


def test_login_truncates_oversized_name_and_phone(client):
    long_name = "N" * 250
    long_phone = "1" * 80
    resp = client.post("/auth/login", json={
        "name": long_name, "email": "toolong@pfizer.com",
        "title": "R&D Manager", "phone": long_phone,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["user"]["name"]) == 200
    assert body["user"]["name"] == long_name[:200]


def test_second_customer_login_does_not_notify_again(client):
    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]

    login_body = {"name": "Dr. Mehta", "email": "anaya@pfizer.com",
                  "title": "R&D Manager", "phone": "+1-555-0100"}
    client.post("/auth/login", json=login_body)
    client.post("/auth/login", json=login_body)  # second login, same user

    resp = client.get("/notifications", headers={"Authorization": f"Bearer {mgr_token}"})
    assert len(resp.json()) == 1  # still just the one, from the first login
