import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ReferenceProduct, ReferenceProductMarket
from app.services import reference_data as rd


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(ReferenceProduct(
        brand="Wegovy", molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water",
        visc_val=1.6, cartridge="1 mL PFS", strengths=["0.25 mg", "1.7 mg"], visc_ref="ref",
        mech_drive="spring_single", mech_dose="fixed", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1 mL PFS", 0.5], "1.7 mg": ["1 mL PFS", 0.75]}, presentations_ref="pref",
    ))
    session.add(ReferenceProductMarket(
        brand="Wegovy", market="EU", device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable",
        mech_label="EU label", ob_ref="EU ob", ob_claims=["EU c"], market_note="Multi-dose pen",
        presentations={"0.25 mg": ["1.5 mL", 1.5]}, pres_ref="EU pref",
    ))
    session.commit()
    yield session
    session.close()


def test_variants_for_unknown_brand_returns_none(db):
    assert rd.variants_for(db, "Nope", "US") is None


def test_variants_for_us_uses_base_profile_with_empty_market_note(db):
    v = rd.variants_for(db, "Wegovy", "US")
    assert v["device"] == "Auto-Injector"
    assert v["mech_drive"] == "spring_single"
    assert v["market_note"] == ""


def test_variants_for_eu_merges_override_over_base(db):
    v = rd.variants_for(db, "Wegovy", "EU")
    assert v["device"] == "Pen Injector"
    assert v["mech_drive"] == "torsion_spring"
    assert v["molecule"] == "Semaglutide"  # non-overridden field falls through from base
    assert v["market_note"] == "Multi-dose pen"


def test_presentation_for_us_uses_base_presentations(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "0.25 mg", "US")
    assert (cart, fill, ref) == ("1 mL PFS", 0.5, "pref")


def test_presentation_for_eu_prefers_market_override(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "0.25 mg", "EU")
    assert (cart, fill, ref) == ("1.5 mL", 1.5, "EU pref")


def test_presentation_for_eu_falls_back_to_base_when_strength_not_overridden(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "1.7 mg", "EU")
    assert (cart, fill, ref) == ("1 mL PFS", 0.75, "pref")


def test_presentation_for_unknown_strength_uses_default(db):
    cart, fill, ref = rd.presentation_for(db, "Wegovy", "9 mg", "US", default_cart="3 mL")
    assert (cart, fill, ref) == ("3 mL", 1.5, "")
