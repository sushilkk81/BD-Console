from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Organization, User, Request


def test_create_org_user_request_roundtrip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    org = Organization(name="Shaily", kind="internal", domain="shaily.com")
    db.add(org)
    db.flush()

    user = User(org_id=org.id, email="a@shaily.com", name="Alice", role="BD Manager")
    db.add(user)
    db.flush()

    req = Request(org_id=org.id, submitted_by=user.id, brand="Ozempic", market="US")
    db.add(req)
    db.commit()

    fetched = db.query(Request).one()
    assert fetched.brand == "Ozempic"
    assert fetched.org_id == org.id
    assert fetched.status == "Awaiting assignment"
