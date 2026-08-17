from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import CustomerVisit, User
from app.schemas import CustomerVisitOut, PageviewIn

router = APIRouter(tags=["customer-visits"])

PAGE_MAX_LEN = 200  # keeps a single pageview entry bounded; not tied to a column width directly


@router.post("/activity/pageview", status_code=204)
def record_pageview(
    payload: PageviewIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("Customer")),
):
    visit = (
        db.query(CustomerVisit)
        .filter_by(session_id=payload.session_id, user_id=current_user.id)
        .first()
    )
    if visit is None:
        raise HTTPException(404, "Session not found")
    page = payload.page[:PAGE_MAX_LEN]
    if page not in visit.pages_visited:
        visit.pages_visited = visit.pages_visited + [page]
        db.commit()


@router.get("/customer-visits", response_model=list[CustomerVisitOut])
def list_customer_visits(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    rows = db.query(CustomerVisit).order_by(CustomerVisit.started_at.desc()).all()
    return [
        CustomerVisitOut(
            id=v.id, org_id=v.org_id, org_name=v.org_name,
            contact_name=v.contact_name, contact_email=v.contact_email,
            contact_phone=v.contact_phone, contact_title=v.contact_title,
            pages_visited=v.pages_visited, started_at=v.started_at,
        )
        for v in rows
    ]
