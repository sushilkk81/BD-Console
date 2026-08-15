from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Organization, User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

INTERNAL_DOMAIN = "shaily.com"
INTERNAL_ROLES = {"BD Manager", "Key Account Manager"}


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    domain = payload.email.split("@", 1)[-1].lower()
    is_internal = domain == INTERNAL_DOMAIN

    if is_internal:
        if payload.role not in INTERNAL_ROLES:
            raise HTTPException(422, f"role must be one of {sorted(INTERNAL_ROLES)} for @{INTERNAL_DOMAIN} emails")
        role = payload.role
        org = db.query(Organization).filter_by(domain=INTERNAL_DOMAIN).first()
        if org is None:
            org = Organization(name="Shaily", kind="internal", domain=INTERNAL_DOMAIN)
            db.add(org)
            db.flush()
    else:
        role = "Customer"
        org = db.query(Organization).filter_by(domain=domain).first()
        if org is None:
            org = Organization(name=domain, kind="customer", domain=domain)
            db.add(org)
            db.flush()

    user = db.query(User).filter_by(email=payload.email).first()
    if user is None:
        user = User(org_id=org.id, email=payload.email, name=payload.name, role=role)
        db.add(user)
        db.flush()
    else:
        user.name = payload.name
        user.role = role

    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.org_id, user.role)
    return LoginResponse(access_token=token, user=UserOut(
        id=user.id, org_id=user.org_id, name=user.name, email=user.email, role=user.role))
