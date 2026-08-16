from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, Organization, OrgKamMap, Request, User
from app.routers.requests import serialize_requests
from app.schemas import AssignKamRequest, KamOut, OrgKamMapOut, OrgKamMapUpdate, RequestOut

router = APIRouter(tags=["kams"])

INTERNAL_DOMAIN = "shaily.com"


def _kams(db: Session) -> list[User]:
    return (
        db.query(User)
        .join(Organization, User.org_id == Organization.id)
        .filter(Organization.domain == INTERNAL_DOMAIN, User.role == "Key Account Manager")
        .order_by(User.name)
        .all()
    )


@router.get("/kams", response_model=list[KamOut])
def list_kams(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    return [KamOut(id=k.id, name=k.name, email=k.email) for k in _kams(db)]


@router.get("/org-kam-map", response_model=list[OrgKamMapOut])
def list_org_kam_map(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    orgs = db.query(Organization).filter(Organization.kind == "customer").order_by(Organization.name).all()
    links = {m.org_id: m.kam_user_id for m in db.query(OrgKamMap).all()}
    kam_ids = set(links.values())
    kam_names = {u.id: u.name for u in db.query(User).filter(User.id.in_(kam_ids))} if kam_ids else {}
    return [
        OrgKamMapOut(
            org_id=o.id, org_name=o.name,
            kam_user_id=links.get(o.id),
            kam_name=kam_names.get(links.get(o.id)),
        )
        for o in orgs
    ]


@router.put("/org-kam-map/{org_id}", response_model=OrgKamMapOut)
def set_org_kam_map(
    org_id: int, payload: OrgKamMapUpdate,
    db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager")),
):
    org = db.get(Organization, org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    kam = db.get(User, payload.kam_user_id)
    if kam is None or kam.role != "Key Account Manager":
        raise HTTPException(422, "kam_user_id must be an existing Key Account Manager")

    link = db.get(OrgKamMap, org_id)
    if link is None:
        link = OrgKamMap(org_id=org_id, kam_user_id=payload.kam_user_id)
        db.add(link)
    else:
        link.kam_user_id = payload.kam_user_id

    db.add(AuditLog(org_id=org_id, actor_user_id=current_user.id, action="org_kam_linked",
                     detail=f"{org.name} → {kam.name}"))
    db.commit()
    return OrgKamMapOut(org_id=org.id, org_name=org.name, kam_user_id=kam.id, kam_name=kam.name)


@router.post("/requests/{request_id}/assign-kam", response_model=RequestOut)
def assign_kam(
    request_id: int, payload: AssignKamRequest,
    db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager")),
):
    req = db.get(Request, request_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    kam = db.get(User, payload.kam_user_id)
    if kam is None or kam.role != "Key Account Manager":
        raise HTTPException(422, "kam_user_id must be an existing Key Account Manager")

    org = db.get(Organization, req.org_id)
    req.assigned_kam_id = kam.id
    req.status = f"Assigned to {kam.name}"
    db.add(AuditLog(org_id=req.org_id, actor_user_id=current_user.id, action="kam_assigned",
                     detail=f"{kam.name} → {org.name if org else req.org_id} ({req.brand})"))
    db.commit()
    return serialize_requests(db, [req])[0]
