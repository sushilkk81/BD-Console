import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Organization, User, Request
from alembic.config import Config
from alembic import command


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


def test_migration_0003_seed_data(tmp_path):
    """Verify migration 0003 creates tables and seeds reference data correctly."""
    # Create a temporary SQLite database file
    db_path = str(tmp_path / "test.db")
    db_url = f"sqlite:///{db_path}"

    # Run migrations
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    command.upgrade(cfg, "head")

    # Connect and verify seed data
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Verify table record counts
        ref_products_count = db.execute(text("SELECT count(*) FROM reference_products")).scalar()
        assert ref_products_count == 11, f"Expected 11 reference_products, got {ref_products_count}"

        ref_markets_count = db.execute(text("SELECT count(*) FROM reference_product_markets")).scalar()
        assert ref_markets_count == 4, f"Expected 4 reference_product_markets, got {ref_markets_count}"

        platforms_count = db.execute(text("SELECT count(*) FROM platform_sheet")).scalar()
        assert platforms_count == 17, f"Expected 17 platform_sheet rows, got {platforms_count}"

        pricing_count = db.execute(text("SELECT count(*) FROM service_pricing")).scalar()
        assert pricing_count == 7, f"Expected 7 service_pricing rows, got {pricing_count}"

        # Spot-check exact values
        ozempic_visc = db.execute(text("SELECT visc_val FROM reference_products WHERE brand = 'Ozempic'")).scalar()
        assert ozempic_visc == 1.4, f"Expected Ozempic visc_val=1.4, got {ozempic_visc}"

        services_pricing = db.execute(text("SELECT payload FROM service_pricing WHERE key = 'SERVICES'")).scalar()
        import json
        services_dict = json.loads(services_pricing)
        assert services_dict == {
            "standard_dv": 200,
            "threshold": 2110,
            "ifu": 1110,
            "human_factor": 400000
        }, f"Unexpected SERVICES pricing: {services_dict}"
    finally:
        db.close()
        engine.dispose()
