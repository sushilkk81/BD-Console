from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Request, User
from app.schemas import RequestCreate, RequestOut

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=RequestOut, status_code=201)
def create_request(payload: RequestCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = Request(org_id=current_user.org_id, submitted_by=current_user.id,
                   brand=payload.brand, market=payload.market, device=payload.device,
                   total=payload.total)
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("", response_model=list[RequestOut])
def list_requests(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Request).filter_by(org_id=current_user.org_id).order_by(Request.created_at.desc()).all()
