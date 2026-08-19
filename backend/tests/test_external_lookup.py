from app.services.external_lookup import cartridge_for_fill


def test_cartridge_for_fill_at_or_below_1_5ml():
    assert cartridge_for_fill(1.5) == "1.5 mL"
    assert cartridge_for_fill(1.0) == "1.5 mL"
    assert cartridge_for_fill(0.5) == "1.5 mL"


def test_cartridge_for_fill_above_1_5ml():
    assert cartridge_for_fill(1.51) == "3 mL"
    assert cartridge_for_fill(3.0) == "3 mL"
