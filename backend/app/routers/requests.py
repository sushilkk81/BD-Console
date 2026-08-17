from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Organization, OrgKamMap, Request, ServiceSelection, SkuRow, User
from app.schemas import RequestCreate, RequestDetailOut, RequestOut, RequestStep1Update, ServiceSelectionOut, SkuRowOut
from app.services import reference_data

router = APIRouter(prefix="/requests", tags=["requests"])


def serialize_requests(db: Session, reqs: list[Request], include_routing: bool = False) -> list[RequestOut]:
    if not reqs:
        return []
    org_ids = {r.org_id for r in reqs}
    orgs = {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(org_ids))}
    org_kam = {m.org_id: m.kam_user_id for m in db.query(OrgKamMap).filter(OrgKamMap.org_id.in_(org_ids))}

    kam_ids = {r.assigned_kam_id for r in reqs if r.assigned_kam_id} | set(org_kam.values())
    kam_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(kam_ids))} if kam_ids else {}

    out = []
    for r in reqs:
        suggested_id = org_kam.get(r.org_id) if include_routing else None
        out.append(RequestOut(
            id=r.id, org_id=r.org_id, org_name=orgs.get(r.org_id, ""),
            submitted_by=r.submitted_by, brand=r.brand, market=r.market, device=r.device,
            status=r.status, total=r.total,
            assigned_kam_id=r.assigned_kam_id,
            assigned_kam_name=kam_names.get(r.assigned_kam_id) if r.assigned_kam_id else None,
            suggested_kam_id=suggested_id,
            suggested_kam_name=kam_names.get(suggested_id) if suggested_id else None,
            viscosity_val=float(r.viscosity_val) if r.viscosity_val is not None else None,
            differentiated=r.differentiated,
            chosen_option=r.chosen_option,
            severity=r.severity,
            timeline_months=r.timeline_months,
            comment=r.comment,
            urgency=r.urgency,
        ))
    return out


def _serialize_detail(db: Session, req: Request, include_routing: bool = False) -> RequestDetailOut:
    base = serialize_requests(db, [req], include_routing=include_routing)[0]
    selections = [sel for row in req.sku_rows for sel in row.service_selections]
    return RequestDetailOut(
        **base.model_dump(),
        sku_rows=[SkuRowOut(id=r.id, strength=r.strength, cartridge=r.cartridge, fill_ml=float(r.fill_ml))
                  for r in req.sku_rows],
        service_selections=[
            ServiceSelectionOut(id=s.id, sku_row_id=s.sku_row_id, standard_dv=s.standard_dv,
                                 threshold=s.threshold, ifu=s.ifu, human_factor=s.human_factor)
            for s in selections
        ],
    )


def _owned_request_or_404(db: Session, request_id: int, user: User) -> Request:
    req = db.get(Request, request_id)
    if req is None or req.submitted_by != user.id:
        raise HTTPException(404, "Request not found")
    return req


def _owned_draft_or_404(db: Session, request_id: int, user: User) -> Request:
    req = _owned_request_or_404(db, request_id, user)
    if req.status != "Draft":
        raise HTTPException(409, "This request is no longer a draft")
    return req


@router.post("", response_model=RequestDetailOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   viscosity_val=payload.viscosity_val, differentiated=payload.differentiated,
                   status="Draft", total=payload.total)
    db.add(req)
    db.flush()

    ref = reference_data.variants_for(db, payload.brand, payload.market)
    default_cart = ref["cartridge"] if ref else "3 mL"
    for strength in payload.strengths:
        cart, fill, _ = reference_data.presentation_for(db, payload.brand, strength, payload.market, default_cart)
        db.add(SkuRow(request_id=req.id, strength=strength, cartridge=cart, fill_ml=fill))

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Request)
    include_routing = False
    if current_user.role == "BD Manager":
        q = q.filter(Request.org_id != current_user.org_id)
        include_routing = True
    elif current_user.role == "Key Account Manager":
        q = q.filter(Request.assigned_kam_id == current_user.id)
        include_routing = True
    else:
        q = q.filter(Request.org_id == current_user.org_id)
    reqs = q.order_by(Request.created_at.desc()).all()
    return serialize_requests(db, reqs, include_routing=include_routing)


def _visible_or_404(db: Session, request_id: int, user: User) -> tuple[Request, bool]:
    """Role-scoped visibility matching list_requests; returns (request, include_routing)."""
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    if user.role == "BD Manager":
        allowed, include_routing = req.org_id != user.org_id, True
    elif user.role == "Key Account Manager":
        allowed, include_routing = req.assigned_kam_id == user.id, True
    else:
        allowed, include_routing = req.org_id == user.org_id, False
    if not allowed:
        raise HTTPException(404, "Request not found")
    return req, include_routing


@router.get("/{request_id}", response_model=RequestDetailOut)
def get_request_detail(request_id: int, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    req, include_routing = _visible_or_404(db, request_id, current_user)
    return _serialize_detail(db, req, include_routing=include_routing)


def _upsert_sku_rows(db: Session, req: Request, rows_in: list) -> bool:
    """Upsert req.sku_rows by strength; returns True if the strength set changed.

    Preserves sku_rows.id (and therefore service_selections) for any strength that's
    still present, so an edit that only tweaks cartridge/fill_ml doesn't orphan an
    already-priced SKU's service selections. See the plan's "implementation decisions"
    note on reconciling the full-replace contract with the service_selections FK.
    """
    existing = {row.strength: row for row in req.sku_rows}
    incoming_strengths = {r.strength for r in rows_in}
    changed = set(existing.keys()) != incoming_strengths

    for strength, row in list(existing.items()):
        if strength not in incoming_strengths:
            db.query(ServiceSelection).filter(ServiceSelection.sku_row_id == row.id).delete()
            db.delete(row)
    db.flush()

    for r in rows_in:
        row = existing.get(r.strength)
        if row is not None and r.strength in incoming_strengths:
            row.cartridge = r.cartridge
            row.fill_ml = r.fill_ml
        else:
            db.add(SkuRow(request_id=req.id, strength=r.strength, cartridge=r.cartridge, fill_ml=r.fill_ml))
    return changed


@router.put("/{request_id}", response_model=RequestDetailOut)
def update_request_step1(request_id: int, payload: RequestStep1Update, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)

    rld_changed = (req.brand != payload.brand or req.market != payload.market
                   or _upsert_sku_rows(db, req, payload.sku_rows))

    req.brand = payload.brand
    req.market = payload.market
    req.viscosity_val = payload.viscosity_val
    req.device = payload.device
    req.differentiated = payload.differentiated

    if rld_changed:
        req.chosen_option = None
        req.severity = None
        req.timeline_months = None

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)
