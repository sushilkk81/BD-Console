from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Organization, OrgKamMap, Request, User
from app.schemas import RequestCreate, RequestOut

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
        ))
    return out


@router.post("", response_model=RequestOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   total=payload.total)
    db.add(req)
    db.commit()
    db.refresh(req)
    return serialize_requests(db, [req], include_routing=False)[0]


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
