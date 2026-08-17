import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db
from app.models import ReferenceProduct


@pytest.fixture
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    session.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "1 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={}, presentations_ref="",
    ))
    session.commit()
    session.close()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100"})
    return resp.json()["access_token"]


def test_reference_products_requires_auth(client):
    assert client.get("/reference-products").status_code == 401


def test_reference_products_lists_seeded_brands(client):
    token = _login(client)
    resp = client.get("/reference-products", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body == [{
        "brand": "Ozempic", "molecule": "Semaglutide", "device": "Pen Injector",
        "strengths": ["0.25 mg", "1 mg"], "visc_val": 1.4, "visc_ref": "ref", "cartridge": "3 mL",
    }]
