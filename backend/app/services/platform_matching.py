"""Mechanism-similarity platform ranking.

Direct port of `mechanism_similarity`, `platform_max_visc`, and `rank_platforms_for_sku`
from the legacy Streamlit app's `data.py`, operating on `PlatformSheet` ORM rows instead
of dicts. Same weights, band thresholds, and drive-adjacency table as the original — see
the org-level-rebuild spec's "no change to the ranking/pricing math" constraint.
"""
from __future__ import annotations

from app.models import PlatformSheet

DRIVE_MANUAL = "manual_dial"
DRIVE_TORSION = "torsion_spring"
DRIVE_SPRING_ONE = "spring_single"
DRIVE_SPRING_AI = "spring_ai"
DRIVE_SPRING_AIHV = "spring_ai_hv"
DRIVE_ON_BODY = "on_body"

PLATFORM_MECH_DRIVE = {
    "Push-Pull": DRIVE_MANUAL, "Geared Pen": DRIVE_MANUAL,
    "Clutch Pen": DRIVE_MANUAL, "Pulley": DRIVE_MANUAL,
    "Torsion Spring": DRIVE_TORSION,
    "3-step AI": DRIVE_SPRING_AI, "2-step AI": DRIVE_SPRING_AI,
    "2-step AI (high visc.)": DRIVE_SPRING_AIHV,
    "On-body device": DRIVE_ON_BODY,
}

DRIVE_ADJACENCY = {
    frozenset((DRIVE_SPRING_AI, DRIVE_SPRING_AIHV)): 0.6,
    frozenset((DRIVE_SPRING_ONE, DRIVE_SPRING_AI)): 0.5,
    frozenset((DRIVE_SPRING_ONE, DRIVE_TORSION)): 0.4,
}

W_ARCH, W_DRIVE, W_DOSE = 0.5, 0.3, 0.2
BAND_CLOSE, BAND_SIMILAR = 0.80, 0.50


def _norm_archetype(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _dose_from_resolution(res: str) -> str:
    r = res.lower()
    if "variable" in r:
        return "variable"
    if "fixed" in r:
        return "fixed"
    return "na"


def platform_signature(p: PlatformSheet) -> dict:
    return {
        "archetype": _norm_archetype(p.cls),
        "drive": PLATFORM_MECH_DRIVE.get(p.mech, ""),
        "dose": _dose_from_resolution(p.resolution),
    }


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


def mechanism_similarity(rld: dict, p: PlatformSheet):
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


def platform_max_visc(p: PlatformSheet) -> float:
    if "high visc" in p.mech.lower():
        return 50.0
    if p.cls == "On-Body":
        return 50.0
    if p.cls == "Pen Injector":
        return 8.0
    return 15.0


def rank_platforms_for_sku(cart: str, rld: dict | None, platforms: list[PlatformSheet]) -> list[dict]:
    """Cartridge-compatible platforms ranked by mechanism closeness, viscosity-aware.

    Hard filter: Close/Similar first (sorted by score). Fallback: Divergent platforms
    appended (tagged fallback=True). Platforms whose viscosity capability is below the
    RLD's viscosity get a soft score penalty (not hidden) and a visc_limited flag. If
    rld has no curated profile, fall back to cartridge-only order with band 'n/a'.
    """
    comp = [p for p in platforms if cart in (p.carts or [])]
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
            s *= 0.5
            why += f"; viscosity {visc} cP exceeds platform capability (~{cap:.0f} cP)"
        band = "Close" if s >= BAND_CLOSE else "Similar" if s >= BAND_SIMILAR else "Divergent"
        scored.append({"platform": p, "score": s, "pct": round(s * 100), "band": band,
                        "rationale": why, "fallback": band == "Divergent", "visc_limited": visc_limited})
    qualifying = sorted((x for x in scored if x["band"] != "Divergent"), key=lambda x: -x["score"])
    fallback = sorted((x for x in scored if x["band"] == "Divergent"), key=lambda x: -x["score"])
    return qualifying + fallback
