from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ReferenceProduct, User
from app.schemas import ReferenceProductOut, ReferenceProductPresentation

router = APIRouter(tags=["reference-products"])


@router.get("/reference-products", response_model=list[ReferenceProductOut])
def list_reference_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    products = db.query(ReferenceProduct).order_by(ReferenceProduct.brand).all()
    return [
        ReferenceProductOut(
            brand=p.brand, molecule=p.molecule, device=p.device, strengths=p.strengths,
            visc_val=float(p.visc_val), visc_ref=p.visc_ref, cartridge=p.cartridge,
            presentations={
                strength: ReferenceProductPresentation(cartridge=pres[0], fill_ml=pres[1])
                for strength, pres in (p.presentations or {}).items()
            },
        )
        for p in products
    ]
