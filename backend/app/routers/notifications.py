from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import Notification, User
from app.schemas import NotificationOut

router = APIRouter(tags=["notifications"])


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, org_id=n.org_id, message=n.message, link_path=n.link_path,
        is_read=n.is_read, created_at=n.created_at,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    rows = (
        db.query(Notification)
        .filter(Notification.recipient_user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return [_out(n) for n in rows]


@router.post("/notifications/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("BD Manager")),
):
    n = db.get(Notification, notification_id)
    if n is None or n.recipient_user_id != current_user.id:
        raise HTTPException(404, "Notification not found")
    n.is_read = True
    db.commit()
    return _out(n)
