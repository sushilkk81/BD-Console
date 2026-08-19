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


@pytest.fixture
def seed_service_pricing(client):
    from app.db import get_db
    from app.models import ServicePricing
    db = next(app.dependency_overrides[get_db]())
    db.add(ServicePricing(key="PKG", payload={"minor": 200, "moderate": 250, "major": 350}))
    db.add(ServicePricing(key="ADD_DV", payload={"value": 50}))
    db.add(ServicePricing(key="TIMELINE", payload={"minor": 3, "moderate": 6, "major": 9}))
    db.add(ServicePricing(key="SERVICES", payload={"standard_dv": 200, "threshold": 2110, "ifu": 1110, "human_factor": 400000}))
    db.commit()
    db.close()


def _login(client, email, name="Test User", role=None):
    body = {"name": name, "email": email}
    if role:
        body["role"] = role
    else:
        body["title"] = "R&D Manager"
        body["phone"] = "+1-555-0100"
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


def test_count_requests_matches_list_and_is_org_scoped(client):
    pfizer_token, _ = _login(client, "anaya@pfizer.com")
    other_token, _ = _login(client, "someone@othercompany.com")

    client.post("/requests", json={"brand": "Ozempic", "market": "US"},
                headers={"Authorization": f"Bearer {pfizer_token}"})
    client.post("/requests", json={"brand": "Ozempic", "market": "EU"},
                headers={"Authorization": f"Bearer {pfizer_token}"})

    resp = client.get("/requests/count", headers={"Authorization": f"Bearer {pfizer_token}"})
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    resp = client.get("/requests/count", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.json()["count"] == 0


def test_count_requests_requires_auth(client):
    resp = client.get("/requests/count")
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


def test_put_request_step1_preserves_service_selections_when_strengths_unchanged(
    client, seed_reference_product, seed_service_pricing,
):
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


def test_put_request_step1_cascades_reset_when_strengths_change(
    client, seed_reference_product, seed_service_pricing,
):
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


def test_put_request_step1_brand_change_upserts_rows_and_cascades_reset(
    client, seed_reference_product, seed_service_pricing,
):
    """Regression test for the short-circuited `or` that skipped _upsert_sku_rows
    whenever brand/market differed — the submitted sku_rows must never be silently
    discarded, and a brand/market change must cascade-reset chosen_option, severity,
    timeline_months, total, and service_selections even when the strength set (and
    therefore the sku_rows.id set) is unchanged.
    """
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
        "brand": "Wegovy", "market": "US", "strengths": ["1 mg"], "viscosity_val": 1.4,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "1 mg", "cartridge": "1 mL PFS", "fill_ml": 0.75}],
    })
    assert resp.status_code == 200
    body = resp.json()

    # The new brand's submitted sku_rows must not be silently discarded.
    assert body["brand"] == "Wegovy"
    assert len(body["sku_rows"]) == 1
    assert body["sku_rows"][0]["cartridge"] == "1 mL PFS"
    assert body["sku_rows"][0]["fill_ml"] == 0.75

    # Brand change cascades a full reset, even though the strength set is unchanged.
    assert body["chosen_option"] is None
    assert body["severity"] is None
    assert body["timeline_months"] is None
    assert body["total"] == 0
    assert body["service_selections"] == []


def test_put_request_step1_new_strength_uses_market_presentation_not_client_value(
    client, seed_reference_product,
):
    """A brand-new SkuRow (strength not previously on this request) must get its
    cartridge/fill_ml from presentation_for(payload.market), ignoring whatever the
    client sent — otherwise adding a strength after a market switch (with no live
    lookup) silently persists base-brand or stale-market presentation data."""
    from app.db import get_db
    from app.models import ReferenceProductMarket
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProductMarket(
        brand="Ozempic", market="South Korea",
        presentations={"1 mg": ["1 mL PFS", 0.9]},
        pres_ref="KR label",
    ))
    db.commit()
    db.close()

    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "South Korea"},
                           headers={"Authorization": f"Bearer {token}"}).json()

    # Client sends a bogus cartridge/fill for the new strength — should be ignored.
    resp = client.put(f"/requests/{created['id']}", headers={"Authorization": f"Bearer {token}"}, json={
        "brand": "Ozempic", "market": "South Korea", "strengths": ["1 mg"], "viscosity_val": None,
        "device": "Pen Injector", "differentiated": False,
        "sku_rows": [{"strength": "1 mg", "cartridge": "3 mL", "fill_ml": 999.0}],
    })
    assert resp.status_code == 200
    row = resp.json()["sku_rows"][0]
    assert row["cartridge"] == "1 mL PFS"
    assert row["fill_ml"] == 0.9


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


def test_put_request_returns_409_when_not_draft(client, seed_reference_product, seed_service_pricing):
    token, _ = _login(client, "anaya@pfizer.com")
    mgr_token, _ = _login(client, "priya@shaily.com", role="BD Manager")
    kam_token, kam_user = _login(client, "mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    sku_id = created["sku_rows"][0]["id"]
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    submitted = client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})
    assert submitted.status_code == 200

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


def test_update_services_computes_minor_severity_pricing(
    client, seed_reference_product, seed_platform_sheet, seed_service_pricing,
):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]

    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"}, json={
        "selections": [{"sku_row_id": sku_id, "standard_dv": True, "threshold": True}],
        "comment": "Bracket into one DV.", "urgency": "Level 1 · call back today",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["severity"] == "minor"          # Neo (torsion-spring pen) is a Close match, not moderate/fallback
    assert body["timeline_months"] == 3
    assert body["total"] == 200_000 + 2110       # 1 DV package (minor lead, no extra SKUs) + 1 threshold
    assert body["comment"] == "Bracket into one DV."


def test_update_services_escalates_severity_for_moderate_platform(
    client, seed_reference_product, seed_service_pricing,
):
    from app.db import get_db
    from app.models import PlatformSheet
    db = next(app.dependency_overrides[get_db]())
    db.add(PlatformSheet(variant="Maxim (Reusable)", family="Maxim", cls="Pen Injector", sub="Reusable",
                          resolution="Fixed Dose – 80 IU", lockout="Yes", carts=["3 mL"],
                          mech="Pulley", color="#2F6E97", moderate=True))
    db.commit()
    db.close()

    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]

    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                       json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})
    assert resp.json()["severity"] == "moderate"


def test_update_services_409_before_option_selected(client, seed_reference_product, seed_service_pricing):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    sku_id = created["sku_rows"][0]["id"]
    resp = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                       json={"selections": [{"sku_row_id": sku_id}]})
    assert resp.status_code == 409


def test_submit_requires_option_and_services(client, seed_reference_product):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    resp = client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 422


def test_submit_flips_status_and_locks_further_edits(
    client, seed_reference_product, seed_platform_sheet, seed_service_pricing,
):
    token, _ = _login(client, "anaya@pfizer.com")
    created = client.post("/requests", json={"brand": "Ozempic", "market": "US", "strengths": ["1 mg"]},
                           headers={"Authorization": f"Bearer {token}"}).json()
    client.post(f"/requests/{created['id']}/select-option", json={"chosen_option": 1},
                headers={"Authorization": f"Bearer {token}"})
    sku_id = created["sku_rows"][0]["id"]
    client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
               json={"selections": [{"sku_row_id": sku_id, "standard_dv": True}]})

    resp = client.post(f"/requests/{created['id']}/submit", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "Awaiting assignment"

    locked = client.put(f"/requests/{created['id']}/services", headers={"Authorization": f"Bearer {token}"},
                         json={"selections": []})
    assert locked.status_code == 409
