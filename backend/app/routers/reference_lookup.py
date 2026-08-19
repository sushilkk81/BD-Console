from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ReferenceProduct, ReferenceProductMarket, User
from app.schemas import (LookedUpStrength, ReferenceStrengthLookupIn, ReferenceStrengthLookupOut,
                          ReferenceViscosityLookupIn, ReferenceViscosityLookupOut)
from app.services.external_lookup import LookupService, get_lookup_service

router = APIRouter(prefix="/reference-lookup", tags=["reference-lookup"])


def _upsert_market_presentations(db: Session, brand: str, market: str, strengths: list[dict]) -> None:
    presentations = {s["strength"]: [s["cartridge"], s["fill_ml"]] for s in strengths}
    row = db.get(ReferenceProductMarket, (brand, market))
    if row is not None:
        row.presentations = presentations
        db.commit()
        return
    try:
        db.add(ReferenceProductMarket(brand=brand, market=market, presentations=presentations))
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(ReferenceProductMarket, (brand, market))
        row.presentations = presentations
        db.commit()


def _create_base_row_if_missing(db: Session, brand: str, molecule: str | None, device: str | None,
                                 strengths: list[dict], citation: str | None) -> None:
    if db.get(ReferenceProduct, brand) is not None:
        return
    presentations = {s["strength"]: [s["cartridge"], s["fill_ml"]] for s in strengths}
    row = ReferenceProduct(
        brand=brand, molecule=molecule or "", device=device or "", dose="", visc="", visc_val=0,
        cartridge=strengths[0]["cartridge"] if strengths else "3 mL",
        strengths=[s["strength"] for s in strengths], visc_ref="",
        mech_drive="", mech_dose="", mech_label="", ob_ref="", ob_claims=[],
        presentations=presentations, presentations_ref=citation or "",
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        db.rollback()  # created concurrently by another request — nothing more to do


@router.post("/strengths", response_model=ReferenceStrengthLookupOut)
def lookup_strengths(payload: ReferenceStrengthLookupIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      svc: LookupService = Depends(get_lookup_service)):
    cached = db.get(ReferenceProductMarket, (payload.brand, payload.market))
    if cached is not None and cached.presentations:
        base = db.get(ReferenceProduct, payload.brand)
        strengths = [
            LookedUpStrength(strength=s, cartridge=v[0], fill_ml=v[1])
            for s, v in cached.presentations.items()
        ]
        return ReferenceStrengthLookupOut(
            found=True, brand=payload.brand,
            molecule=base.molecule if base else None, device=base.device if base else None,
            strengths=strengths, citation=cached.pres_ref,
        )

    result = svc.lookup_strengths(payload.brand, payload.market)
    if not result.found:
        return ReferenceStrengthLookupOut(found=False, brand=payload.brand)

    _create_base_row_if_missing(db, payload.brand, result.molecule, result.device,
                                 result.strengths, result.citation)
    _upsert_market_presentations(db, payload.brand, payload.market, result.strengths)

    return ReferenceStrengthLookupOut(
        found=True, brand=payload.brand, molecule=result.molecule, device=result.device,
        strengths=[LookedUpStrength(**s) for s in result.strengths], citation=result.citation,
    )


@router.post("/viscosity", response_model=ReferenceViscosityLookupOut)
def lookup_viscosity(payload: ReferenceViscosityLookupIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      svc: LookupService = Depends(get_lookup_service)):
    base = db.get(ReferenceProduct, payload.brand)
    if base is not None and base.visc_val:
        return ReferenceViscosityLookupOut(
            found=True, brand=payload.brand, visc_val=float(base.visc_val), citation=base.visc_ref,
        )

    result = svc.lookup_viscosity(payload.brand, payload.molecule)
    if not result.found:
        return ReferenceViscosityLookupOut(found=False, brand=payload.brand)

    if base is not None:
        base.visc_val = result.visc_val
        base.visc_ref = result.citation or ""
        db.commit()

    return ReferenceViscosityLookupOut(
        found=True, brand=payload.brand, visc_val=result.visc_val, citation=result.citation,
    )
