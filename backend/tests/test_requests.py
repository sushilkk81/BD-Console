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


@pytest.fixture
def seed_reference_product(client):
    from app.db import get_db
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1.5 mL", 1.5], "0.5 mg": ["1.5 mL", 1.5], "1 mg": ["3 mL", 3.0], "2 mg": ["3 mL", 3.0]},
        presentations_ref="pref",
    ))
    db.commit()
    db.close()


@pytest.fixture
def seed_platform_sheet(client):
    from app.db import get_db
    from app.models import PlatformSheet
    db = next(app.dependency_overrides[get_db]())
    db.add(PlatformSheet(variant="Neo (3 mL)", family="Neo", cls="Pen Injector", sub="Disposable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Torsion Spring", color="#7DB343", moderate=False))
    db.add(PlatformSheet(variant="Axiom", family="Axiom", cls="Pen Injector", sub="Disposable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Push-Pull", color="#8FBF52", moderate=False))
    db.commit()
    db.close()


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
    assert resp.json()["status"] == "Draft"

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


def test_customer_does_not_see_suggested_kam_routing_data(client):
    pfizer_token, pfizer_user = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")

    # Link the org to a suggested KAM so suggested_kam_id would be non-null if leaked.
    client.put(f"/org-kam-map/{pfizer_user['org_id']}", json={"kam_user_id": kam_user["id"]},
               headers={"Authorization": f"Bearer {mgr_token}"})

    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {pfizer_token}"}).json()
    assert created["suggested_kam_id"] is None
    assert created["suggested_kam_name"] is None

    listed = client.get("/requests", headers={"Authorization": f"Bearer {pfizer_token}"}).json()
    assert listed[0]["suggested_kam_id"] is None
    assert listed[0]["suggested_kam_name"] is None

    # But BD Manager and KAM still see routing data.
    mgr_view = client.get("/requests", headers={"Authorization": f"Bearer {mgr_token}"}).json()
    assert any(r["suggested_kam_id"] == kam_user["id"] for r in mgr_view)

    assign_resp = client.post(f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]},
                               headers={"Authorization": f"Bearer {mgr_token}"})
    assert assign_resp.json()["suggested_kam_id"] == kam_user["id"]

    kam_view = client.get("/requests", headers={"Authorization": f"Bearer {kam_token}"}).json()
    assert kam_view[0]["suggested_kam_id"] == kam_user["id"]


def test_create_request_defaults_to_draft_status(client):
    token, _ = _login(client, "anaya@pfizer.com")
    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "Draft"
    assert resp.json()["sku_rows"] == []


def test_create_request_with_strengths_seeds_sku_rows_from_reference_data(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    resp = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                        headers={"Authorization": f"Bearer {token}"})
    body = resp.json()
    assert len(body["sku_rows"]) == 1
    assert body["sku_rows"][0] == {"id": body["sku_rows"][0]["id"], "strength": "1 mg", "cartridge": "3 mL", "fill_ml": 3.0}


def test_get_request_detail_not_found_for_non_owner_customer(client):
    token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 404


def test_get_request_detail_visible_to_bd_manager_and_assigned_kam(client):
    token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()

    assert client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {mgr_token}"}).status_code == 200

    not_assigned = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {kam_token}"})
    assert not_assigned.status_code == 404

    client.post(f"/requests/{created['id']}/assign-kam", json={"kam_user_id": kam_user["id"]},
                headers={"Authorization": f"Bearer {mgr_token}"})
    assigned = client.get(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {kam_token}"})
    assert assigned.status_code == 200


def test_put_request_step1_upserts_sku_rows_and_computes_total_fields(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg", "2 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [
            {"strength": "1 mg", "cartridge": "1.5 mL", "fill_ml": 2.0},  # edited cartridge/fill, id preserved
            {"strength": "2 mg", "cartridge": "3 mL", "fill_ml": 3.0},    # new row
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    rows_by_strength = {r["strength"]: r for r in body["sku_rows"]}
    assert rows_by_strength["1 mg"]["id"] == created["sku_rows"][0]["id"]
    assert rows_by_strength["1 mg"]["cartridge"] == "1.5 mL"
    assert rows_by_strength["2 mg"]["fill_ml"] == 3.0


def test_put_request_step1_preserves_service_selections_when_strengths_unchanged(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True, "threshold": True}],
    })

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "1 mg", "cartridge": "1 mL PFS", "fill_ml": 0.75}],  # only cartridge/fill changed
    })
    body = resp.json()
    assert body["chosen_option"] == 1  # not reset — strengths didn't change
    assert len(body["service_selections"]) == 1


def test_put_request_step1_cascades_reset_when_strengths_change(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True}],
    })

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["2 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "2 mg", "cartridge": "3 mL", "fill_ml": 3.0}],
    })
    body = resp.json()
    assert body["chosen_option"] is None
    assert body["severity"] is None
    assert body["service_selections"] == []


def test_put_request_step1_rejects_unknown_cartridge(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": ["1 mg"], "sku_rows": [
            {"strength": "1 mg", "cartridge": "9 mL bogus", "fill_ml": 3.0},
        ],
    })
    assert resp.status_code == 422


def test_put_request_returns_404_for_non_owner(client):
    token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {other_token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": [], "sku_rows": [],
    })
    assert resp.status_code == 404


def test_put_request_returns_409_when_not_draft(client):
    token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": []})
    client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})

    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "US", "strengths": [], "sku_rows": [],
    })
    assert resp.status_code == 409


def test_get_platform_options_ranks_by_mechanism_closeness(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()

    resp = client.get(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    options = resp.json()["options"]
    assert options["1"][0]["platform"] == "Neo (3 mL)"  # torsion-spring pen closest to Ozempic's RLD
    assert options["1"][0]["band"] == "Close"


def test_get_platform_options_422_without_sku_rows(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.get(f"/requests/{created['id']}/platform-options", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_select_option_persists_choice(client, seed_reference_product, seed_platform_sheet):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 2},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["chosen_option"] == 2


def test_select_option_rejects_out_of_range(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 4},
                        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422
