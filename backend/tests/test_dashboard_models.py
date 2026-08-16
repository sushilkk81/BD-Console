from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import AuditLog, DashboardMetric, Organization, OrgKamMap, Request, User


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_request_can_be_assigned_to_a_kam():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    pfizer = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add_all([shaily, pfizer])
    db.flush()

    kam = User(org_id=shaily.id, email="mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    customer = User(org_id=pfizer.id, email="anaya@pfizer.com", name="Dr. Mehta", role="Customer")
    db.add_all([kam, customer])
    db.flush()

    req = Request(org_id=pfizer.id, submitted_by=customer.id, brand="Ozempic", market="US")
    db.add(req)
    db.flush()
    req.assigned_kam_id = kam.id
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.assigned_kam_id == kam.id


def test_org_kam_map_links_org_to_kam():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    pfizer = Organization(name="Pfizer", kind="customer", domain="pfizer.com")
    db.add_all([shaily, pfizer])
    db.flush()

    kam = User(org_id=shaily.id, email="mah@shaily.com", name="Mr. MAH", role="Key Account Manager")
    db.add(kam)
    db.flush()

    db.add(OrgKamMap(org_id=pfizer.id, kam_user_id=kam.id))
    db.commit()

    link = db.query(OrgKamMap).one()
    assert link.kam_user_id == kam.id


def test_audit_log_roundtrip():
    db = _session()
    shaily = Organization(name="Shaily", kind="internal", domain="shaily.com")
    db.add(shaily)
    db.flush()
    actor = User(org_id=shaily.id, email="priya@shaily.com", name="Ms. Priya", role="BD Manager")
    db.add(actor)
    db.flush()

    db.add(AuditLog(org_id=None, actor_user_id=actor.id, action="kam_assigned", detail="test"))
    db.commit()

    row = db.query(AuditLog).one()
    assert row.action == "kam_assigned"
    assert row.created_at is not None


def test_dashboard_metric_stores_json_payload():
    db = _session()
    db.add(DashboardMetric(key="quarterly_target", payload={"Q1": 32, "Q2": 36}))
    db.commit()

    row = db.query(DashboardMetric).one()
    assert row.payload == {"Q1": 32, "Q2": 36}
