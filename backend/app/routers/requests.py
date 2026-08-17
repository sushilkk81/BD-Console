from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_role
from app.models import (Organization, OrgKamMap, PlatformSheet, Request, RequestMessage, ServicePricing,
                         ServiceSelection, SkuRow, User)
from app.schemas import (BdReviewIn, KamAssessmentIn, MessageIn, MessageOut, PlatformOptionRow, PlatformOptionsOut,
                          RequestCreate, RequestDetailOut, RequestOut, RequestStep1Update, RespondToCustomerIn,
                          SelectOptionRequest, ServiceSelectionOut, ServicesUpdate, SkuRowOut)
from app.services import platform_matching, reference_data

router = APIRouter(prefix="/requests", tags=["requests"])

COMMENT_MAX_LEN = 2000  # matches Request.comment column width (models.py)
URGENCY_MAX_LEN = 100  # matches Request.urgency column width (models.py)
STATUS_MAX_LEN = 50  # matches Request.status column width (models.py)
MESSAGE_MAX_LEN = 2000  # matches RequestMessage.body column width (models.py)


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
            kam_cost_usd=float(r.kam_cost_usd) if r.kam_cost_usd is not None else None,
            kam_timeline_months=r.kam_timeline_months,
            kam_notes=r.kam_notes,
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


def _assigned_kam_or_404(db: Session, request_id: int, user: User) -> Request:
    req = db.get(Request, request_id)
    if req is None or req.assigned_kam_id != user.id:
        raise HTTPException(404, "Request not found")
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

    rows_changed = _upsert_sku_rows(db, req, payload.sku_rows)
    rld_changed = req.brand != payload.brand or req.market != payload.market or rows_changed

    req.brand = payload.brand
    req.market = payload.market
    req.viscosity_val = payload.viscosity_val
    req.device = payload.device
    req.differentiated = payload.differentiated

    if rld_changed:
        req.chosen_option = None
        req.severity = None
        req.timeline_months = None
        req.total = 0
        db.flush()
        sku_row_ids = {r.id for r in req.sku_rows}
        if sku_row_ids:
            db.query(ServiceSelection).filter(ServiceSelection.sku_row_id.in_(sku_row_ids)).delete(
                synchronize_session=False)

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


def _scoring_rld(db: Session, req: Request) -> dict | None:
    """Market-effective RLD profile, honouring a differentiated-device override."""
    rld = reference_data.variants_for(db, req.brand, req.market)
    if rld is None:
        return None
    if req.differentiated and req.device:
        rld = dict(rld)
        rld["device"] = req.device
    return rld


def _option_tables(db: Session, req: Request) -> dict[int, list[PlatformOptionRow]]:
    """{1,2,3} -> per-SKU row at that rank, mirroring the legacy app's _option_tables."""
    rld = _scoring_rld(db, req)
    platforms = db.query(PlatformSheet).order_by(PlatformSheet.variant).all()
    ranked_by_sku = {
        row.strength: platform_matching.rank_platforms_for_sku(row.cartridge, rld, platforms)
        for row in req.sku_rows
    }
    tables: dict[int, list[PlatformOptionRow]] = {1: [], 2: [], 3: []}
    for opt in range(3):
        for row in req.sku_rows:
            ranked = ranked_by_sku[row.strength]
            item = ranked[opt] if opt < len(ranked) else None
            p = item["platform"] if item else None
            tables[opt + 1].append(PlatformOptionRow(
                sku=row.strength, cartridge=row.cartridge,
                platform=p.variant if p else None,
                cls=p.cls if p else None, sub=(p.sub or None) if p else None,
                resolution=p.resolution if p else None, lockout=p.lockout if p else None,
                mech=p.mech if p else None,
                band=item["band"] if item else "n/a",
                pct=item["pct"] if item else None,
                fallback=bool(item and item["fallback"]),
                visc_limited=bool(item and item["visc_limited"]),
            ))
    return tables


@router.get("/{request_id}/platform-options", response_model=PlatformOptionsOut)
def get_platform_options(request_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    req = _owned_request_or_404(db, request_id, current_user)
    if not req.sku_rows:
        raise HTTPException(422, "Add at least one SKU on step 1 before viewing platform options")
    tables = _option_tables(db, req)
    return PlatformOptionsOut(options={str(k): v for k, v in tables.items()})


@router.post("/{request_id}/select-option", response_model=RequestDetailOut)
def select_option(request_id: int, payload: SelectOptionRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    req.chosen_option = payload.chosen_option
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.put("/{request_id}/services", response_model=RequestDetailOut)
def update_services(request_id: int, payload: ServicesUpdate, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    if req.chosen_option is None:
        raise HTTPException(409, "Select a platform option before configuring services")

    sku_row_ids = {r.id for r in req.sku_rows}
    for sel in payload.selections:
        if sel.sku_row_id not in sku_row_ids:
            raise HTTPException(422, f"sku_row_id {sel.sku_row_id} does not belong to this request")

    chosen_rows = _option_tables(db, req)[req.chosen_option]
    has_fallback = any(row.fallback for row in chosen_rows)
    chosen_platforms = {row.platform for row in chosen_rows if row.platform}
    moderate_variants = {
        p.variant for p in db.query(PlatformSheet).filter(PlatformSheet.moderate.is_(True),
                                                            PlatformSheet.variant.in_(chosen_platforms))
    } if chosen_platforms else set()
    severity = "moderate" if (has_fallback or moderate_variants) else "minor"

    pricing = {row.key: row.payload for row in db.query(ServicePricing).all()}
    pkg, add_dv, timeline, services_cost = (
        pricing["PKG"], pricing["ADD_DV"]["value"], pricing["TIMELINE"], pricing["SERVICES"],
    )

    db.query(ServiceSelection).filter(ServiceSelection.sku_row_id.in_(sku_row_ids)).delete(synchronize_session=False)
    db.flush()
    for sel in payload.selections:
        db.add(ServiceSelection(sku_row_id=sel.sku_row_id, standard_dv=sel.standard_dv,
                                 threshold=sel.threshold, ifu=sel.ifu, human_factor=sel.human_factor))

    n_dv = sum(1 for sel in payload.selections if sel.standard_dv)
    lead = pkg[severity]
    dv_usd = (lead + add_dv * max(0, n_dv - 1)) * 1000 if n_dv else 0
    thr = sum(1 for sel in payload.selections if sel.threshold) * services_cost["threshold"]
    ifu = sum(1 for sel in payload.selections if sel.ifu) * services_cost["ifu"]
    hf = sum(1 for sel in payload.selections if sel.human_factor) * services_cost["human_factor"]

    req.severity = severity
    req.timeline_months = timeline[severity]
    req.comment = payload.comment[:COMMENT_MAX_LEN] if payload.comment else payload.comment
    req.urgency = payload.urgency[:URGENCY_MAX_LEN] if payload.urgency else payload.urgency
    req.total = dv_usd + thr + ifu + hf

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.post("/{request_id}/submit", response_model=RequestDetailOut)
def submit_request(request_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = _owned_draft_or_404(db, request_id, current_user)
    has_selections = any(row.service_selections for row in req.sku_rows)
    if req.chosen_option is None or not has_selections:
        raise HTTPException(422, "Select a platform option and configure services before submitting")
    req.status = "Awaiting assignment"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req)


@router.post("/{request_id}/kam-assessment", response_model=RequestDetailOut)
def submit_kam_assessment(request_id: int, payload: KamAssessmentIn, db: Session = Depends(get_db),
                           current_user: User = Depends(require_role("Key Account Manager"))):
    req = _assigned_kam_or_404(db, request_id, current_user)
    expected = f"Assigned to {current_user.name}"[:STATUS_MAX_LEN]
    if req.status not in (expected, "Revision Requested"):
        raise HTTPException(409, "This request isn't awaiting a KAM assessment")

    req.kam_cost_usd = payload.kam_cost_usd
    req.kam_timeline_months = payload.kam_timeline_months
    req.kam_notes = payload.kam_notes
    req.status = "KAM Assessment Submitted"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)


@router.post("/{request_id}/bd-review", response_model=RequestDetailOut)
def bd_review(request_id: int, payload: BdReviewIn, db: Session = Depends(get_db),
              current_user: User = Depends(require_role("BD Manager"))):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    if req.status != "KAM Assessment Submitted":
        raise HTTPException(409, "This request isn't awaiting BD Manager review")

    if payload.decision == "approve":
        req.status = "Approved — Awaiting KAM Response"
    else:
        db.add(RequestMessage(request_id=req.id, channel="internal", sender_user_id=current_user.id,
                               body=payload.note[:MESSAGE_MAX_LEN]))
        req.status = "Revision Requested"

    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)


@router.post("/{request_id}/respond-to-customer", response_model=RequestDetailOut)
def respond_to_customer(request_id: int, payload: RespondToCustomerIn, db: Session = Depends(get_db),
                         current_user: User = Depends(require_role("Key Account Manager"))):
    req = _assigned_kam_or_404(db, request_id, current_user)
    if req.status != "Approved — Awaiting KAM Response":
        raise HTTPException(409, "This request isn't ready to respond to the customer")

    db.add(RequestMessage(request_id=req.id, channel="customer", sender_user_id=current_user.id,
                           body=payload.message[:MESSAGE_MAX_LEN]))
    req.status = "Responded to Customer"
    db.commit()
    db.refresh(req)
    return _serialize_detail(db, req, include_routing=True)


@router.post("/{request_id}/messages", response_model=MessageOut, status_code=201)
def post_message(request_id: int, payload: MessageIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")

    if current_user.role == "BD Manager":
        raise HTTPException(403, "BD Manager can view messages but not post them")
    elif current_user.role == "Key Account Manager":
        if req.assigned_kam_id != current_user.id:
            raise HTTPException(404, "Request not found")
        if payload.channel == "customer" and req.status == "Customer Query":
            req.status = "Responded to Customer"
    else:
        if req.submitted_by != current_user.id:
            raise HTTPException(404, "Request not found")
        if payload.channel != "customer":
            raise HTTPException(422, "Customers may only post to the customer channel")
        if req.status not in ("Responded to Customer", "Customer Query"):
            raise HTTPException(409, "This request isn't open for customer messages yet")
        req.status = "Customer Query"

    msg = RequestMessage(request_id=req.id, channel=payload.channel, sender_user_id=current_user.id,
                          body=payload.body[:MESSAGE_MAX_LEN])
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return MessageOut(id=msg.id, request_id=msg.request_id, channel=msg.channel,
                       sender_user_id=msg.sender_user_id, sender_name=current_user.name,
                       body=msg.body, created_at=msg.created_at)


@router.get("/{request_id}/messages", response_model=list[MessageOut])
def list_messages(request_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    req, _ = _visible_or_404(db, request_id, current_user)
    q = db.query(RequestMessage).filter(RequestMessage.request_id == req.id)
    if current_user.role not in ("BD Manager", "Key Account Manager"):
        q = q.filter(RequestMessage.channel == "customer")
    msgs = q.order_by(RequestMessage.created_at).all()

    sender_ids = {m.sender_user_id for m in msgs}
    names = {u.id: u.name for u in db.query(User).filter(User.id.in_(sender_ids))} if sender_ids else {}
    return [
        MessageOut(id=m.id, request_id=m.request_id, channel=m.channel, sender_user_id=m.sender_user_id,
                   sender_name=names.get(m.sender_user_id, ""), body=m.body, created_at=m.created_at)
        for m in msgs
    ]
