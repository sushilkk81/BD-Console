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


def _login_customer(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100"})
    body = resp.json()
    return body["access_token"], body["session_id"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_pageview_requires_customer_role(client):
    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    resp = client.post("/activity/pageview", json={"session_id": "x", "page": "/requests"},
                        headers=_auth(mgr_token))
    assert resp.status_code == 403


def test_customer_visits_rejects_customer_role(client):
    customer_token, _ = _login_customer(client, "anaya@pfizer.com")
    resp = client.get("/customer-visits", headers=_auth(customer_token))
    assert resp.status_code == 403


def test_pageview_rejects_foreign_session_id(client):
    token, _ = _login_customer(client, "anaya@pfizer.com")
    resp = client.post("/activity/pageview", json={"session_id": "not-mine", "page": "/requests"},
                        headers=_auth(token))
    assert resp.status_code == 404


def test_pageview_appends_distinct_pages(client):
    token, session_id = _login_customer(client)
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests"},
                headers=_auth(token))
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests/1"},
                headers=_auth(token))
    client.post("/activity/pageview", json={"session_id": session_id, "page": "/requests"},
                headers=_auth(token))  # repeat — should not duplicate

    mgr_token = client.post("/auth/login", json={
        "name": "Priya", "email": "priya@shaily.com", "role": "BD Manager"}).json()["access_token"]
    resp = client.get("/customer-visits", headers=_auth(mgr_token))
    visit = resp.json()[0]
    assert visit["pages_visited"] == ["/requests", "/requests/1"]
