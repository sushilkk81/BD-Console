import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import CustomerVisit, Notification, Organization, User
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.security import create_token

router = APIRouter(prefix="/auth", tags=["auth"])

INTERNAL_DOMAIN = "shaily.com"
INTERNAL_ROLES = {"BD Manager", "Key Account Manager"}
CUSTOMER_TITLES = {"R&D Manager", "BD Manager"}
MESSAGE_MAX_LEN = 300  # matches Notification.message column width (models.py)
LINK_PATH_MAX_LEN = 200  # matches Notification.link_path column width (models.py)
NAME_MAX_LEN = 200  # matches User.name / CustomerVisit.contact_name column width (models.py)
PHONE_MAX_LEN = 50  # matches User.phone / CustomerVisit.contact_phone column width (models.py)


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
        if payload.title not in CUSTOMER_TITLES:
            raise HTTPException(422, f"title must be one of {sorted(CUSTOMER_TITLES)}")
        if not payload.phone:
            raise HTTPException(422, "phone is required")
        role = "Customer"
        org = db.query(Organization).filter_by(domain=domain).first()
        if org is None:
            org = Organization(name=domain, kind="customer", domain=domain)
            db.add(org)
            db.flush()

    user = db.query(User).filter_by(email=payload.email).first()
    if user is None:
        user = User(org_id=org.id, email=payload.email, name=payload.name[:NAME_MAX_LEN], role=role)
        db.add(user)
        db.flush()
    else:
        user.name = payload.name[:NAME_MAX_LEN]
        user.role = role
    if not is_internal:
        user.title = payload.title
        user.phone = payload.phone[:PHONE_MAX_LEN]

    session_id = None
    if not is_internal:
        db.flush()
        is_first_login = db.query(CustomerVisit).filter_by(user_id=user.id).first() is None
        session_id = str(uuid.uuid4())
        visit = CustomerVisit(
            user_id=user.id, org_id=org.id, session_id=session_id,
            contact_name=user.name, contact_email=user.email,
            contact_phone=user.phone, contact_title=user.title,
            org_name=org.name, pages_visited=[],
        )
        db.add(visit)
        db.flush()
        if is_first_login:
            bd_managers = (
                db.query(User)
                .join(Organization, User.org_id == Organization.id)
                .filter(Organization.domain == INTERNAL_DOMAIN, User.role == "BD Manager")
                .all()
            )
            message = f"{user.name} ({org.name}) logged in for the first time"[:MESSAGE_MAX_LEN]
            link_path = f"/dashboard/manager/customers?visit={visit.id}"[:LINK_PATH_MAX_LEN]
            for mgr in bd_managers:
                db.add(Notification(
                    recipient_user_id=mgr.id, org_id=org.id, customer_visit_id=visit.id,
                    message=message, link_path=link_path,
                ))

    db.commit()
    db.refresh(user)

    token = create_token(user.id, user.org_id, user.role)
    return LoginResponse(
        access_token=token,
        user=UserOut(id=user.id, org_id=user.org_id, org_name=org.name, name=user.name,
                     email=user.email, role=user.role),
        session_id=session_id,
    )
