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


def test_notifications_requires_bd_manager_role(client):
    kam_token, _ = _login(client, "mah@shaily.com", role="Key Account Manager")
    resp = client.get("/notifications", headers=_auth(kam_token))
    assert resp.status_code == 403


def test_notifications_scoped_to_recipient(client):
    mgr1_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    mgr2_token, _ = _login(client, "rahul@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")  # first customer login — notifies both managers

    resp1 = client.get("/notifications", headers=_auth(mgr1_token)).json()
    resp2 = client.get("/notifications", headers=_auth(mgr2_token)).json()
    assert len(resp1) == 1
    assert len(resp2) == 1
    assert resp1[0]["id"] != resp2[0]["id"]  # separate rows, not shared


def test_mark_notification_read(client):
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    notif_id = client.get("/notifications", headers=_auth(mgr_token)).json()[0]["id"]
    resp = client.post(f"/notifications/{notif_id}/read", headers=_auth(mgr_token))
    assert resp.status_code == 200
    assert resp.json()["is_read"] is True


def test_mark_notification_read_rejects_other_managers_row(client):
    mgr1_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    mgr2_token, _ = _login(client, "rahul@shaily.com", role="BD Manager")
    _login(client, "anaya@pfizer.com")

    mgr1_notif_id = client.get("/notifications", headers=_auth(mgr1_token)).json()[0]["id"]
    resp = client.post(f"/notifications/{mgr1_notif_id}/read", headers=_auth(mgr2_token))
    assert resp.status_code == 404
