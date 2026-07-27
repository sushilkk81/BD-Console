"""Domain data & engines for the Shaily DDCP Console (Streamlit build)."""
from __future__ import annotations

# ---- Brand palette ----
BRAND = {
    "blue": "#2F6E97", "blue_dk": "#234F70", "petal_blue": "#3D7CA6",
    "green": "#7DB343", "forest": "#2E7D46", "orange": "#E5883B", "gray": "#6D6E71",
    "bg": "#F5F8F8", "ink": "#0E1B24", "ink2": "#3A4C57", "muted": "#6B7C86",
    "line": "#DCE6E6", "surface": "#FFFFFF",
    "minor": "#2E7D46", "moderate": "#E5883B", "major": "#C0392B",
}

# ── Device-mechanism layer (curated; FDA Orange Book device-patent grounded) ──
# Drive families reflect the PATENT-DISCLOSED mechanism, not the apparent one.
DRIVE_MANUAL      = "manual_dial"     # dial/geared pen, manual button-push force
DRIVE_TORSION     = "torsion_spring"  # torsion-spring auto-delivery pen (e.g. FlexTouch)
DRIVE_SPRING_ONE  = "spring_single"   # single-dose spring pen
DRIVE_SPRING_AI   = "spring_ai"       # spring-driven auto-injector
DRIVE_SPRING_AIHV = "spring_ai_hv"    # high-force spring AI (viscous mAb)
DRIVE_ON_BODY     = "on_body"         # on-body / electromechanical

# Shaily platform `mech` label → drive family
PLATFORM_MECH_DRIVE = {
    "Push-Pull": DRIVE_MANUAL, "Geared Pen": DRIVE_MANUAL,
    "Clutch Pen": DRIVE_MANUAL, "Pulley": DRIVE_MANUAL,
    "Torsion Spring": DRIVE_TORSION,
    "3-step AI": DRIVE_SPRING_AI, "2-step AI": DRIVE_SPRING_AI,
    "2-step AI (high visc.)": DRIVE_SPRING_AIHV,
    "On-body device": DRIVE_ON_BODY,
}


def _norm_archetype(s: str) -> str:
    """Normalise 'Auto-Injector' / 'Autoinjector' / 'Pen Injector' to a comparable token."""
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _dose_from_resolution(res: str) -> str:
    r = res.lower()
    if "variable" in r:
        return "variable"
    if "fixed" in r:
        return "fixed"
    return "na"


def platform_signature(p: dict) -> dict:
    """Mechanism signature for a Shaily platform, derived from existing sheet fields."""
    return {
        "archetype": _norm_archetype(p["cls"]),
        "drive": PLATFORM_MECH_DRIVE.get(p["mech"], ""),
        "dose": _dose_from_resolution(p["resolution"]),
    }


# ---- Reference products (public-literature derived) ----
REFERENCE_PRODUCTS = {
    "Ozempic":   dict(molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg", "0.5 mg", "1 mg", "2 mg"], visc_ref="DailyMed SmPC (NDC 0169-4181); aqueous GLP-1 solution",
                 mech_drive=DRIVE_TORSION, mech_dose="variable", mech_label="FlexTouch dial pen — torsion-spring + lead-screw",
                 ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
                 ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"]),
    "Wegovy":    dict(molecule="Semaglutide", device="Auto-Injector", dose="fixed", visc="water", visc_val=1.6, cartridge="1 mL PFS", strengths=["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"], visc_ref="FDA label 215256; single-dose AI",
                 mech_drive=DRIVE_SPRING_ONE, mech_dose="fixed", mech_label="Single-dose spring pen",
                 ob_ref="FDA Orange Book device patents — Wegovy single-dose pen (Novo Nordisk); exact patent nos. to confirm",
                 ob_claims=["Pre-set fixed dose", "Spring-assisted single delivery"]),
    "Trulicity": dict(molecule="Dulaglutide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=6.2, cartridge="1 mL PFS", strengths=["0.75 mg", "1.5 mg", "3 mg", "4.5 mg"], visc_ref="Lilly label; mAb fusion, elevated viscosity",
                 mech_drive=DRIVE_SPRING_AI, mech_dose="fixed", mech_label="Single-dose auto-injector (2-step, hidden needle)",
                 ob_ref="FDA Orange Book device patents — Trulicity single-dose AI (Lilly); exact patent nos. to confirm",
                 ob_claims=["Spring-driven auto-injection", "Automatic needle insertion + retraction", "Single fixed dose"]),
    "Mounjaro":  dict(molecule="Tirzepatide", device="Auto-Injector", dose="fixed", visc="higher", visc_val=5.0, cartridge="1 mL PFS", strengths=["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"], visc_ref="Lilly KwikPen literature",
                 mech_drive=DRIVE_SPRING_AI, mech_dose="fixed", mech_label="Single-dose auto-injector",
                 ob_ref="FDA Orange Book device patents — Mounjaro single-dose AI (Lilly); exact patent nos. to confirm",
                 ob_claims=["Spring-driven auto-injection", "Push-on-skin activation", "Single fixed dose"]),
    "Victoza":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg"], visc_ref="EMA SmPC; multi-dose pen",
                 mech_drive=DRIVE_TORSION, mech_dose="variable", mech_label="FlexTouch-type dial pen — torsion-spring",
                 ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
                 ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"]),
    "Saxenda":   dict(molecule="Liraglutide", device="Pen Injector", dose="variable", visc="water", visc_val=1.5, cartridge="3 mL", strengths=["0.6 mg", "1.2 mg", "1.8 mg", "2.4 mg", "3 mg"], visc_ref="EMA SmPC; weight-management pen",
                 mech_drive=DRIVE_TORSION, mech_dose="variable", mech_label="FlexTouch dial pen — torsion-spring + lead-screw",
                 ob_ref="FDA Orange Book device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
                 ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set variable dose"]),
    "Toujeo":    dict(molecule="Insulin glargine U300", device="Pen Injector", dose="variable", visc="water", visc_val=1.8, cartridge="1.5 mL", strengths=["300 U/mL"], visc_ref="Sanofi label; basal insulin",
                 mech_drive=DRIVE_MANUAL, mech_dose="variable", mech_label="SoloStar-type dial pen — manual lead-screw",
                 ob_ref="FDA Orange Book device patents — SoloStar platform (Sanofi); exact patent nos. to confirm",
                 ob_claims=["Manual dial-set variable dose", "Lead-screw plunger advance", "Button-push delivery"]),
    "Lantus":    dict(molecule="Insulin glargine", device="Pen Injector", dose="variable", visc="water", visc_val=1.7, cartridge="3 mL", strengths=["100 U/mL"], visc_ref="Sanofi label; basal insulin",
                 mech_drive=DRIVE_MANUAL, mech_dose="variable", mech_label="SoloStar dial pen — manual lead-screw",
                 ob_ref="FDA Orange Book device patents — SoloStar platform (Sanofi); exact patent nos. to confirm",
                 ob_claims=["Manual dial-set variable dose", "Lead-screw plunger advance", "Button-push delivery"]),
    "Humira":    dict(molecule="Adalimumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=12.5, cartridge="1 mL PFS", strengths=["10 mg", "20 mg", "40 mg", "80 mg"], visc_ref="AbbVie label; high-viscosity mAb",
                 mech_drive=DRIVE_SPRING_AIHV, mech_dose="fixed", mech_label="High-viscosity mAb auto-injector",
                 ob_ref="FDA Orange Book device patents — Humira pen/AI (AbbVie); exact patent nos. to confirm",
                 ob_claims=["Spring-driven auto-injection", "High-force delivery for viscous mAb", "Single fixed dose"]),
    "Enbrel":    dict(molecule="Etanercept", device="Auto-Injector", dose="fixed", visc="higher", visc_val=9.0, cartridge="1 mL PFS", strengths=["25 mg", "50 mg"], visc_ref="Amgen label; mAb",
                 mech_drive=DRIVE_SPRING_AI, mech_dose="fixed", mech_label="mAb auto-injector (SureClick-type)",
                 ob_ref="FDA Orange Book device patents — SureClick platform (Amgen); exact patent nos. to confirm",
                 ob_claims=["Spring-driven auto-injection", "Automatic needle insertion", "Single fixed dose"]),
    "Dupixent":  dict(molecule="Dupilumab", device="Auto-Injector", dose="fixed", visc="higher", visc_val=8.5, cartridge="3 mL PFS", strengths=["200 mg", "300 mg"], visc_ref="Regeneron label; mAb",
                 mech_drive=DRIVE_SPRING_AI, mech_dose="fixed", mech_label="mAb auto-injector / pre-filled pen",
                 ob_ref="FDA Orange Book device patents — Dupixent pen (Regeneron/Sanofi); exact patent nos. to confirm",
                 ob_claims=["Spring-driven auto-injection", "Pre-filled single dose", "Automatic delivery"]),
}

CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"]

# ---- Per-SKU presentation (cartridge × fill in mL), curated from FDA/EMA labels ----
# Each brand maps strength → (cartridge, fill_mL); "_ref" is the label citation.
PRESENTATIONS = {
    "Ozempic": {"_ref": "Ozempic FDA label 209637 / DailyMed — 2 mg/1.5 mL, 4 mg/3 mL, 8 mg/3 mL pens",
                "0.25 mg": ("1.5 mL", 1.5), "0.5 mg": ("1.5 mL", 1.5),
                "1 mg": ("3 mL", 3.0), "2 mg": ("3 mL", 3.0)},
    "Wegovy": {"_ref": "Wegovy PI (Novo Nordisk) — single-dose pens 0.5 mL (≤1 mg), 0.75 mL (1.7/2.4 mg)",
               "0.25 mg": ("1 mL PFS", 0.5), "0.5 mg": ("1 mL PFS", 0.5), "1 mg": ("1 mL PFS", 0.5),
               "1.7 mg": ("1 mL PFS", 0.75), "2.4 mg": ("1 mL PFS", 0.75)},
    "Trulicity": {"_ref": "Trulicity FDA label 125469 — single-dose pen 0.5 mL, all doses",
                  "0.75 mg": ("1 mL PFS", 0.5), "1.5 mg": ("1 mL PFS", 0.5),
                  "3 mg": ("1 mL PFS", 0.5), "4.5 mg": ("1 mL PFS", 0.5)},
    "Mounjaro": {"_ref": "Mounjaro DailyMed — single-dose pen 0.5 mL, all doses",
                 "2.5 mg": ("1 mL PFS", 0.5), "5 mg": ("1 mL PFS", 0.5), "7.5 mg": ("1 mL PFS", 0.5),
                 "10 mg": ("1 mL PFS", 0.5), "12.5 mg": ("1 mL PFS", 0.5), "15 mg": ("1 mL PFS", 0.5)},
    "Victoza": {"_ref": "Victoza DailyMed — 18 mg/3 mL multi-dose pen",
                "0.6 mg": ("3 mL", 3.0), "1.2 mg": ("3 mL", 3.0), "1.8 mg": ("3 mL", 3.0)},
    "Saxenda": {"_ref": "Saxenda EMA SmPC — 18 mg/3 mL multi-dose pen",
                "0.6 mg": ("3 mL", 3.0), "1.2 mg": ("3 mL", 3.0), "1.8 mg": ("3 mL", 3.0),
                "2.4 mg": ("3 mL", 3.0), "3 mg": ("3 mL", 3.0)},
    "Toujeo": {"_ref": "Toujeo DailyMed — SoloStar 1.5 mL (450 U), U-300",
               "300 U/mL": ("1.5 mL", 1.5)},
    "Lantus": {"_ref": "Lantus DailyMed — SoloStar 3 mL (300 U), U-100",
               "100 U/mL": ("3 mL", 3.0)},
    "Humira": {"_ref": "Humira IFU/label — citrate-free 40 mg/0.4 mL, 80 mg/0.8 mL, 20 mg/0.2 mL, 10 mg/0.1 mL",
               "10 mg": ("1 mL PFS", 0.1), "20 mg": ("1 mL PFS", 0.2),
               "40 mg": ("1 mL PFS", 0.4), "80 mg": ("1 mL PFS", 0.8)},
    "Enbrel": {"_ref": "Enbrel FDA label 103795 — SureClick 50 mg/1.0 mL, 25 mg/0.5 mL",
               "25 mg": ("1 mL PFS", 0.5), "50 mg": ("1 mL PFS", 1.0)},
    "Dupixent": {"_ref": "Dupixent DailyMed — pre-filled pen 200 mg/1.14 mL, 300 mg/2 mL",
                 "200 mg": ("3 mL PFS", 1.14), "300 mg": ("3 mL PFS", 2.0)},
}


def presentation_for(brand: str, strength: str, market: str = None, default_cart: str = "3 mL"):
    """Return (cartridge, fill_mL, citation) for an RLD SKU, market-aware.

    A (brand, market) override in MARKET_VARIANTS wins; else the base PRESENTATIONS
    apply; else (default_cart, 1.5, "") for an unknown brand/strength.
    """
    ov = MARKET_VARIANTS.get((brand, market)) if market else None
    if ov and ov.get("presentations", {}).get(strength):
        cart, fill = ov["presentations"][strength]
        return cart, fill, ov.get("pres_ref", "")
    p = PRESENTATIONS.get(brand, {})
    cart, fill = p.get(strength, (default_cart, 1.5))
    return cart, fill, p.get("_ref", "")


# ---- Market-specific RLD overrides (US / EU / Canada) ------------------------
# Keyed by (brand, market); merged over the base REFERENCE_PRODUCTS entry. Only the
# products whose DEVICE/mechanism/presentation genuinely differ by market appear here.
# Rule: verify every variant against the latest innovator PIL; keep DATA_AS_OF current.
_WEGOVY_EU = dict(
    device="Pen Injector", mech_drive=DRIVE_TORSION, mech_dose="variable",
    mech_label="Wegovy FlexTouch multi-dose pen — torsion-spring",
    ob_ref="EMA/FDA device patents — FlexTouch platform (Novo Nordisk); exact patent nos. to confirm",
    ob_claims=["Torsion-spring energy store", "Lead-screw plunger advance", "Dial-set dose", "Multi-dose reusable pen"],
    presentations={s: ("1.5 mL", 1.5) for s in ["0.25 mg", "0.5 mg", "1 mg", "1.7 mg", "2.4 mg"]},
    pres_ref="EMA Wegovy SmPC — FlexTouch multi-dose pen, 1.5 mL (all strengths)",
    note="Multi-dose FlexTouch pen (1.5 mL) — differs from US single-dose")
_MOUNJARO_MD = dict(
    device="Pen Injector", mech_drive=DRIVE_MANUAL, mech_dose="fixed",
    mech_label="Mounjaro KwikPen — multi-dose (4 × 0.6 mL)",
    ob_ref="EMA device patents — KwikPen platform (Lilly); exact patent nos. to confirm",
    ob_claims=["Manual dial/push delivery", "Fixed 0.6 mL dose", "Multi-dose (4 doses/pen)"],
    presentations={s: ("3 mL", 2.4) for s in ["2.5 mg", "5 mg", "7.5 mg", "10 mg", "12.5 mg", "15 mg"]},
    pres_ref="EMA Mounjaro SmPC — KwikPen 2.4 mL (4 × 0.6 mL)",
    note="KwikPen multi-dose (4 doses/pen) — differs from US single-dose")

MARKET_VARIANTS = {
    ("Wegovy", "EU"): dict(_WEGOVY_EU),
    ("Wegovy", "Canada"): dict(_WEGOVY_EU, pres_ref="Health Canada Wegovy Product Monograph — FlexTouch multi-dose pen"),
    ("Mounjaro", "EU"): dict(_MOUNJARO_MD),
    ("Mounjaro", "Canada"): dict(_MOUNJARO_MD, pres_ref="Health Canada Mounjaro KwikPen IFU — 2.4 mL (4 × 0.6 mL)"),
}


def variants_for(brand: str, market: str):
    """Effective RLD profile for a (brand, market): base merged with any market override.

    Adds 'market_note' (str, empty if none). Returns None for an unknown brand.
    """
    base = REFERENCE_PRODUCTS.get(brand)
    if base is None:
        return None
    eff = dict(base)
    ov = MARKET_VARIANTS.get((brand, market))
    if ov:
        for k, v in ov.items():
            if k not in ("note", "pres_ref", "presentations"):
                eff[k] = v
    eff["market_note"] = ov.get("note", "") if ov else ""
    return eff

# ---- Shaily platform sheet (authoritative) ----
# cls: Pen Injector | Autoinjector | On-Body ; carts: compatible cartridge sizes
PLATFORM_SHEET = [
    dict(family="Axiom",     variant="Axiom",              cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Push-Pull",    color="#8FBF52"),
    dict(family="Axiom Max", variant="Axiom Max",          cls="Pen Injector", sub="Disposable", resolution="Fixed – 80 IU",                      lockout="Yes", carts=["3 mL", "1.5 mL"],     mech="Push-Pull",    color="#E5883B"),
    dict(family="Protean",   variant="Protean P3",         cls="Pen Injector", sub="Disposable", resolution="Variable – 3 dose settings – 80 IU", lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean P5",         cls="Pen Injector", sub="Disposable", resolution="Variable – 5 dose settings – 80 IU", lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean P60",        cls="Pen Injector", sub="Disposable", resolution="Fixed – 60 IU",                      lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean PS1",        cls="Pen Injector", sub="Disposable", resolution="Fixed – only 1 dose",                lockout="Yes", carts=["1.5 mL"],              mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Protean",   variant="Protean PR60",       cls="Pen Injector", sub="Reusable",   resolution="Fixed – 60 IU",                      lockout="Yes", carts=["3 mL"],                mech="Geared Pen",   color="#5FA0C4"),
    dict(family="Neo",       variant="Neo (3 mL)",         cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Torsion Spring", color="#7DB343"),
    dict(family="Neo",       variant="Neo (1.5 mL)",       cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",              lockout="Yes", carts=["1.5 mL"],              mech="Torsion Spring", color="#7DB343"),
    dict(family="Harmony",   variant="Harmony HS1",        cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Clutch Pen",   color="#3D7CA6"),
    dict(family="Harmony",   variant="Harmony H2",         cls="Pen Injector", sub="Disposable", resolution="Variable Dose – 80 IU",              lockout="Yes", carts=["1.5 mL"],              mech="Clutch Pen",   color="#3D7CA6"),
    dict(family="Maxim",     variant="Maxim (Disposable)", cls="Pen Injector", sub="Disposable", resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Pulley",       color="#2F6E97"),
    dict(family="Maxim",     variant="Maxim (Reusable)",   cls="Pen Injector", sub="Reusable",   resolution="Fixed Dose – 80 IU",                 lockout="Yes", carts=["3 mL"],                mech="Pulley",       color="#2F6E97", moderate=True),
    dict(family="Tristan",   variant="Tristan",            cls="Autoinjector", sub="",           resolution="0.2 – 1 mL",                         lockout="N/A", carts=["1 mL PFS"],           mech="3-step AI",    color="#234F70"),
    dict(family="Toby",      variant="Toby",               cls="Autoinjector", sub="",           resolution="0.2 – 2.25 mL",                      lockout="N/A", carts=["1 mL PFS", "3 mL PFS"], mech="2-step AI",  color="#2E7D46"),
    dict(family="Safe-LAN",  variant="Safe LAN",           cls="Autoinjector", sub="",           resolution="0.5 mL",                             lockout="N/A", carts=["1 mL Bespoke"],       mech="2-step AI (high visc.)", color="#C0392B"),
    dict(family="Mira",      variant="Mira",               cls="On-Body",      sub="",           resolution="0.5 – 20 mL",                        lockout="N/A", carts=["1 mL Bespoke"],       mech="On-body device", color="#6D6E71"),
]


def platforms_for_cartridge(cart: str):
    """Compatible platforms for a cartridge size, in presentation order (Option 1..n)."""
    return [p for p in PLATFORM_SHEET if cart in p["carts"]]


# Partial-credit adjacency between drive families (symmetric); same drive = 1.0, absent pair = 0.0
DRIVE_ADJACENCY = {
    frozenset((DRIVE_SPRING_AI, DRIVE_SPRING_AIHV)): 0.6,
    frozenset((DRIVE_SPRING_ONE, DRIVE_SPRING_AI)): 0.5,
    frozenset((DRIVE_SPRING_ONE, DRIVE_TORSION)): 0.4,
    frozenset((DRIVE_TORSION, DRIVE_MANUAL)): 0.2,
    frozenset((DRIVE_SPRING_ONE, DRIVE_MANUAL)): 0.2,
}

W_ARCH, W_DRIVE, W_DOSE = 0.5, 0.3, 0.2
BAND_CLOSE, BAND_SIMILAR = 0.80, 0.50


def _drive_match(a: str, b: str) -> float:
    if a and a == b:
        return 1.0
    return DRIVE_ADJACENCY.get(frozenset((a, b)), 0.0)


def _dose_match(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a == "na" or b == "na":
        return 0.5
    return 0.0


def mechanism_similarity(rld: dict, p: dict):
    """Return (score 0..1, band, rationale) comparing an RLD profile to a platform."""
    sig = platform_signature(p)
    arch = 1.0 if _norm_archetype(rld["device"]) == sig["archetype"] else 0.0
    drv = _drive_match(rld.get("mech_drive", ""), sig["drive"])
    dose = _dose_match(rld.get("mech_dose", ""), sig["dose"])
    score = W_ARCH * arch + W_DRIVE * drv + W_DOSE * dose
    band = "Close" if score >= BAND_CLOSE else "Similar" if score >= BAND_SIMILAR else "Divergent"
    parts = [
        "same archetype" if arch else "different archetype",
        "same drive" if drv == 1.0 else "related drive" if drv > 0 else "unrelated drive",
        "dose match" if dose == 1.0 else "dose n/a" if dose == 0.5 else "dose differs",
    ]
    return score, band, "; ".join(parts)


# Approx. max solution viscosity each platform class can deliver (cP), for soft-filtering.
def platform_max_visc(p: dict) -> float:
    if "high visc" in p["mech"].lower():
        return 50.0                    # Safe-LAN — high-force AI for viscous mAbs
    if p["cls"] == "On-Body":
        return 50.0                    # Mira — on-body, high viscosity / large volume
    if p["cls"] == "Pen Injector":
        return 8.0                     # spring/manual pens — aqueous low-viscosity
    return 15.0                        # standard auto-injectors


def rank_platforms_for_sku(cart: str, rld: "dict | None"):
    """Cartridge-compatible platforms ranked by mechanism closeness, viscosity-aware.

    Hard filter: Close/Similar first (sorted by score). Fallback: Divergent
    platforms appended (tagged fallback=True) so a 3-slot view can still fill
    when fewer than 3 qualify. Platforms whose viscosity capability is below the
    RLD's viscosity get a soft score penalty (not hidden) and a visc_limited flag.
    If rld has no curated profile, fall back to cartridge-only order with band 'n/a'.
    """
    comp = platforms_for_cartridge(cart)
    if not rld or not rld.get("mech_drive"):
        return [{"platform": p, "score": None, "pct": None, "band": "n/a",
                 "rationale": "no curated mechanism profile", "fallback": False, "visc_limited": False}
                for p in comp]
    visc = rld.get("visc_val")
    scored = []
    for p in comp:
        s, _band, why = mechanism_similarity(rld, p)
        cap = platform_max_visc(p)
        visc_limited = bool(visc and visc > cap)
        if visc_limited:
            s *= 0.5                    # soft penalty — deprioritise, don't hide
            why += f"; viscosity {visc} cP exceeds platform capability (~{cap:.0f} cP)"
        band = "Close" if s >= BAND_CLOSE else "Similar" if s >= BAND_SIMILAR else "Divergent"
        scored.append({"platform": p, "score": s, "pct": round(s * 100), "band": band,
                       "rationale": why, "fallback": band == "Divergent", "visc_limited": visc_limited})
    qualifying = sorted((x for x in scored if x["band"] != "Divergent"), key=lambda x: -x["score"])
    fallback = sorted((x for x in scored if x["band"] == "Divergent"), key=lambda x: -x["score"])
    return qualifying + fallback


# ---- Cost / timelines / services ----
PKG = {"minor": 200, "moderate": 250, "major": 350}   # K USD, governing DV
ADD_DV = 50
TIMELINE = {"minor": 3, "moderate": 6, "major": 9}
SEV_LABEL = {"minor": "Minor change", "moderate": "Moderate change", "major": "Major change"}
SEV_LOGIC = {
    "minor": "Minor tool modification + tool validation",
    "moderate": "Up to 2 tool modifications + tool validation",
    "major": "> 2 tool modifications + tool validation",
}
SERVICES = dict(standard_dv=200, threshold=2110, ifu=1110, human_factor=400000)  # USD (standard_dv in K)
STD_CONDITION_TESTS = [
    "Deliverable Volume (ISO 11608-1)", "Dose Accuracy — rear", "Dose Accuracy — middle",
    "Dose Accuracy — end", "Last-dose lock-out", "Injection force (ISO 11608-1)",
]


def commercial_fy(sub_fy: str, sub_q: str) -> str:
    y = int("".join(ch for ch in sub_fy if ch.isdigit()))
    q = int("".join(ch for ch in sub_q if ch.isdigit()) or "1")
    total = y * 4 + (q - 1) + 10
    return f"FY{total // 4} Q{(total % 4) + 1}"


MARKETS = ["US", "EU", "Canada"]
DATA_AS_OF = "2026-07-23"   # RLD label/PIL verification date (refresh when variants change)
FY_OPTIONS = [f"FY{y}" for y in range(26, 32)]
QUARTERS = ["Q1", "Q2", "Q3", "Q4"]

# ═══════════════════════════════════════════════════════════════════════════
# BD organisation & command-centre data (from the client org tables)
# ═══════════════════════════════════════════════════════════════════════════
BD_MANAGER = "Ms. Priya (BD Manager)"
REPS = ["Mr. MAH", "Mr. HEN", "Mr. MUK", "Mr. FED", "Ms. SUK"]
PLATFORM_COLS = ["Toby", "Neo", "Harmony", "Axiom", "Axiom Max", "Protean", "Tristan", "Mira", "Safe-LAN"]
CUSTOMERS = ["Auro", "DRL", "Sand", "Dem", "Shun", "Homo", "Chem", "McD", "Torr"]
REP_REGION = {"Mr. MAH": "India", "Mr. HEN": "Europe", "Mr. MUK": "Asia", "Mr. FED": "North America", "Ms. SUK": "Europe"}

# Quarter-wise expected business per rep ($M)
REP_QUARTERLY = {
    "Mr. MAH": {"Q1": 8, "Q2": 10, "Q3": 9, "Q4": 12},
    "Mr. HEN": {"Q1": 6, "Q2": 7, "Q3": 8, "Q4": 9},
    "Mr. MUK": {"Q1": 5, "Q2": 6, "Q3": 7, "Q4": 8},
    "Mr. FED": {"Q1": 7, "Q2": 6, "Q3": 9, "Q4": 10},
    "Ms. SUK": {"Q1": 4, "Q2": 5, "Q3": 6, "Q4": 7},
}
QUARTER_TARGET = {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}
NEW_CUSTOMERS_QTR = {"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}

# Rep × platform business ($M) — which rep drives which platform
REP_PLATFORM = {
    "Mr. MAH": {"Neo": 12, "Toby": 11},
    "Mr. HEN": {"Harmony": 9, "Axiom": 9},
    "Mr. MUK": {"Protean": 8, "Axiom Max": 6},
    "Mr. FED": {"Toby": 10, "Tristan": 10},
    "Ms. SUK": {"Mira": 7, "Safe-LAN": 7},
}
# Rep × customer (business partner) business ($M)
REP_CUSTOMER = {
    "Mr. MAH": {"Auro": 14, "McD": 9},
    "Mr. HEN": {"DRL": 11, "Chem": 7},
    "Mr. MUK": {"Sand": 8, "Torr": 6},
    "Mr. FED": {"Dem": 12, "Homo": 8},
    "Ms. SUK": {"Shun": 9, "Chem": 5},
}
# Expected production output per Shaily variant (million units) from combined demand
PRODUCTION = {"Toby": 21, "Neo": 34, "Harmony": 18, "Axiom": 12, "Axiom Max": 9,
              "Protean": 15, "Tristan": 7, "Mira": 4, "Safe-LAN": 6}

EVENTS = [
    dict(name="CPHI Worldwide", city="Frankfurt", date="Oct 2026", tag="Exhibiting"),
    dict(name="PDA Universe of Pre-filled Syringes", city="Vienna", date="Nov 2026", tag="Speaking"),
    dict(name="PODD — Drug Delivery Partnerships", city="Boston", date="Oct 2026", tag="Booth"),
    dict(name="DDL — Drug Delivery to the Lungs", city="Edinburgh", date="Dec 2026", tag="Attending"),
]

# Workforce view (individual reps) — promptness + call log
WORKFORCE = [
    dict(id="mah", name="Mr. MAH", region="India", promptness=92,
         calls=[("2026-07-20", "Auro — Neo 4-SKU sampling"), ("2026-07-15", "McD — Toby DV scope"), ("2026-07-08", "Auro — pricing review")]),
    dict(id="hen", name="Mr. HEN", region="Europe", promptness=85,
         calls=[("2026-07-19", "DRL — Harmony CRF walkthrough"), ("2026-07-09", "Chem — Axiom intro")]),
    dict(id="muk", name="Mr. MUK", region="Asia", promptness=88,
         calls=[("2026-07-17", "Sand — Protean fit"), ("2026-07-05", "Torr — Axiom Max enquiry")]),
    dict(id="fed", name="Mr. FED", region="North America", promptness=80,
         calls=[("2026-07-18", "Dem — Toby PFS review"), ("2026-07-12", "Homo — Tristan scoping")]),
    dict(id="suk", name="Ms. SUK", region="Europe", promptness=90,
         calls=[("2026-07-14", "Shun — Mira on-body demo"), ("2026-07-06", "Chem — Safe-LAN viscosity")]),
]


def relationship_score(w) -> int:
    recency = min(100, 60 + len(w["calls"]) * 8) if w["calls"] else 40
    return round(recency * 0.6 + w["promptness"] * 0.4)


# ═══════════════════════════════════════════════════════════════════════════
# Key Account Managers (KAM)  — renamed from "BD Workforce"
# Each KAM has a unique login (real auth is a Phase-2 backend feature).
# ═══════════════════════════════════════════════════════════════════════════
KAMS = {
    "mah": dict(id="mah", name="Mr. MAH", login="mah@shaily.com"),
    "muk": dict(id="muk", name="Mr. MUK", login="muk@shaily.com"),
    "han": dict(id="han", name="Mr. HAN", login="han@shaily.com"),
    "fed": dict(id="fed", name="Mr. FED", login="fed@shaily.com"),
}
KAM_REGIONS = ["India (South Region)", "India (North Region)", "Europe", "Asia (other than India)"]
# Region → KAM (default assignment)
REGION_KAM = {
    "India (South Region)": "mah",
    "India (North Region)": "muk",
    "Europe": "han",
    "Asia (other than India)": "fed",
}
# Organization-specific KAM overrides (for bigger organizations)
ORG_KAM = {"SANDOX": "muk", "Pfizer": "mah", "DEMO": "han", "Pharmathen": "han"}


def resolve_kam(org=None, region=None, region_map=None, org_map=None):
    """Organization override wins; otherwise fall back to the region mapping."""
    om = org_map if org_map is not None else ORG_KAM
    rm = region_map if region_map is not None else REGION_KAM
    if org and org in om:
        return om[org], "organization"
    if region and region in rm:
        return rm[region], "region"
    return None, None


# Deliverable / pre-requisite catalogue for the KAM schedule
DELIVERABLES = [
    dict(item="User Requirement Document", resp="Customer", upload=False),
    dict(item="Component drawings & specifications", resp="KAM", upload=True,
         components=["Cartridge holder", "Pen Body", "Pen Cap"]),
    dict(item="Cartridge Drawings (fill volume & tolerances, plunger-stopper position)", resp="KAM", upload=True),
    dict(item="PFS Drawings (fill volume & tolerances, plunger-stopper position)", resp="KAM", upload=True),
    dict(item="Filled Cartridges", resp="Customer", upload=False),
    dict(item="Filled PFS", resp="Customer", upload=False),
    dict(item="Assembly Guide for the Customer", resp="KAM", upload=True),
    dict(item="Design Verification Package", resp="KAM", upload=True),
    dict(item="Aging Study Package", resp="KAM", upload=True),
    dict(item="DMF filing", resp="KAM", upload=False),
    dict(item="Functionality Failure related queries", resp="Customer", upload=False, query=True),
]
FY_QUARTERS = [f"{fy} {q}" for fy in ["FY26", "FY27", "FY28"] for q in ["Q1", "Q2", "Q3", "Q4"]]

# Demo customer queries (BD Manager inbox)
SAMPLE_QUERIES = [
    dict(id="q1", org="Pfizer", region="Europe", date="2026-07-22",
         product="Semaglutide (Ozempic ref)", note="4 SKUs — need Neo mapping + costing"),
    dict(id="q2", org="SANDOX", region="India (North Region)", date="2026-07-24",
         product="Liraglutide (Victoza ref)", note="Harmony 3 mL, 3 SKUs"),
    dict(id="q3", org="Pharmathen", region="Europe", date="2026-07-26",
         product="Dulaglutide (Trulicity ref)", note="AI Toby, 2 SKUs"),
]
