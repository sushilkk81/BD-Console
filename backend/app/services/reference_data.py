"""Reference-product lookups backing the request wizard.

Ports `variants_for` and `presentation_for` from the legacy app's data.py onto the
seeded `reference_products` / `reference_product_markets` tables (Task 1 migration).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ReferenceProduct, ReferenceProductMarket

_OVERRIDABLE = ["device", "mech_drive", "mech_dose", "mech_label", "ob_ref", "ob_claims"]


def variants_for(db: Session, brand: str, market: str) -> dict | None:
    """Effective RLD profile for a (brand, market): base merged with any market override."""
    base = db.get(ReferenceProduct, brand)
    if base is None:
        return None
    eff = {
        "brand": base.brand, "molecule": base.molecule, "device": base.device,
        "dose": base.dose, "visc": base.visc, "visc_val": float(base.visc_val),
        "cartridge": base.cartridge, "strengths": base.strengths, "visc_ref": base.visc_ref,
        "mech_drive": base.mech_drive, "mech_dose": base.mech_dose, "mech_label": base.mech_label,
        "ob_ref": base.ob_ref, "ob_claims": base.ob_claims,
    }
    ov = db.get(ReferenceProductMarket, (brand, market))
    if ov is not None:
        for key in _OVERRIDABLE:
            val = getattr(ov, key)
            if val:
                eff[key] = val
    eff["market_note"] = (ov.market_note or "") if ov is not None else ""
    return eff


def presentation_for(db: Session, brand: str, strength: str, market: str, default_cart: str = "3 mL"):
    """Return (cartridge, fill_mL, citation) for an RLD SKU, market-aware.

    A (brand, market) override wins for the strengths it covers; else the base
    presentations apply; else (default_cart, 1.5, "") for an unknown brand/strength.
    """
    ov = db.get(ReferenceProductMarket, (brand, market))
    if ov is not None and ov.presentations and strength in ov.presentations:
        cart, fill = ov.presentations[strength]
        return cart, fill, ov.pres_ref or ""
    base = db.get(ReferenceProduct, brand)
    presentations = base.presentations if base else {}
    if strength in presentations:
        cart, fill = presentations[strength]
        return cart, fill, base.presentations_ref
    return default_cart, 1.5, ""
