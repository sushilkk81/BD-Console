from app.models import PlatformSheet
from app.services import platform_matching as pm


def _platform(**kw):
    defaults = dict(variant="test", family="test", cls="Pen Injector", sub="", resolution="Variable Dose – 80 IU",
                     lockout="Yes", carts=["3 mL"], mech="Torsion Spring", color="#000", moderate=False)
    defaults.update(kw)
    return PlatformSheet(**defaults)


WEGOVY_RLD = dict(device="Auto-Injector", mech_drive="spring_single", mech_dose="fixed", visc_val=1.6)


def test_same_archetype_drive_dose_scores_close():
    toby = _platform(variant="Toby", cls="Autoinjector", mech="2-step AI", resolution="Fixed Dose – 0.2 – 2.25 mL", carts=["1 mL PFS"])
    score, band, _ = pm.mechanism_similarity(WEGOVY_RLD, toby)
    # arch differs (Auto-Injector vs Autoinjector normalise equal), drive spring_single~spring_ai=0.5, dose fixed==fixed
    assert band in ("Close", "Similar")
    assert score == pm.W_ARCH * 1.0 + pm.W_DRIVE * 0.5 + pm.W_DOSE * 1.0


def test_unrelated_drive_and_archetype_scores_divergent():
    # Use On-Body platform with on_body drive which has no adjacency entries at all in DRIVE_ADJACENCY
    mira = _platform(variant="Mira", cls="On-Body", mech="On-body device", resolution="Fixed Dose – 1 – 5 mL", carts=["1 mL Cartridge"])
    score, band, _ = pm.mechanism_similarity(WEGOVY_RLD, mira)
    # arch: auto-injector != on-body (0.0), drive: spring_single vs on_body has no adjacency entry (0.0), dose: fixed == fixed (1.0)
    assert band == "Divergent"
    assert score == pm.W_ARCH * 0.0 + pm.W_DRIVE * 0.0 + pm.W_DOSE * 1.0


def test_platform_max_visc_by_class():
    assert pm.platform_max_visc(_platform(cls="Pen Injector")) == 8.0
    assert pm.platform_max_visc(_platform(cls="Autoinjector", mech="2-step AI")) == 15.0
    assert pm.platform_max_visc(_platform(cls="Autoinjector", mech="2-step AI (high visc.)")) == 50.0
    assert pm.platform_max_visc(_platform(cls="On-Body", mech="On-body device")) == 50.0


def test_rank_platforms_for_sku_soft_penalises_visc_limited_platform():
    low_visc_pen = _platform(variant="Neo", cls="Pen Injector", mech="Torsion Spring", carts=["3 mL"])
    high_visc_rld = dict(device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable", visc_val=20.0)
    ranked = pm.rank_platforms_for_sku("3 mL", high_visc_rld, [low_visc_pen])
    assert ranked[0]["visc_limited"] is True
    assert ranked[0]["score"] == 1.0 * 0.5  # perfect match halved by the soft penalty


def test_rank_platforms_for_sku_filters_by_cartridge_and_orders_qualifying_before_fallback():
    close = _platform(variant="Neo", cls="Pen Injector", mech="Torsion Spring", carts=["3 mL"])
    divergent = _platform(variant="Axiom", cls="Autoinjector", mech="Push-Pull", resolution="Fixed Dose – 80 IU", carts=["3 mL"])
    wrong_cart = _platform(variant="Tristan", cls="Autoinjector", mech="3-step AI", carts=["1 mL PFS"])
    rld = dict(device="Pen Injector", mech_drive="torsion_spring", mech_dose="variable", visc_val=1.5)
    ranked = pm.rank_platforms_for_sku("3 mL", rld, [close, divergent, wrong_cart])
    assert [r["platform"].variant for r in ranked] == ["Neo", "Axiom"]
    assert ranked[0]["fallback"] is False
    assert ranked[1]["fallback"] is True


def test_rank_platforms_for_sku_falls_back_to_cartridge_only_without_curated_profile():
    p = _platform(variant="Neo", carts=["3 mL"])
    ranked = pm.rank_platforms_for_sku("3 mL", None, [p])
    assert ranked == [{"platform": p, "score": None, "pct": None, "band": "n/a",
                        "rationale": "no curated mechanism profile", "fallback": False, "visc_limited": False}]
