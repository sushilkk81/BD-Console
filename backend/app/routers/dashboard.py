from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_role
from app.models import AuditLog, DashboardMetric, Organization, Request, User
from app.schemas import AuditLogOut, DashboardMetricsOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

METRIC_KEYS = [
    "quarterly_target", "new_customers_qtr", "platform_production",
    "rep_quarterly", "rep_platform_matrix", "rep_customer_matrix",
]


@router.get("/metrics", response_model=DashboardMetricsOut)
def get_metrics(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    rows = {m.key: m.payload for m in db.query(DashboardMetric).filter(DashboardMetric.key.in_(METRIC_KEYS))}

    status_counts: dict[str, int] = {}
    total = 0
    for (status,) in db.query(Request.status).filter(Request.org_id != current_user.org_id):
        status_counts[status] = status_counts.get(status, 0) + 1
        total += 1

    return DashboardMetricsOut(
        quarterly_target=rows.get("quarterly_target", {}),
        new_customers_qtr=rows.get("new_customers_qtr", {}),
        platform_production=rows.get("platform_production", {}),
        rep_quarterly=rows.get("rep_quarterly", {}),
        rep_platform_matrix=rows.get("rep_platform_matrix", {}),
        rep_customer_matrix=rows.get("rep_customer_matrix", {}),
        live={"requests_by_status": status_counts, "total_requests": total},
    )


@router.get("/audit-log", response_model=list[AuditLogOut])
def get_audit_log(db: Session = Depends(get_db), current_user: User = Depends(require_role("BD Manager"))):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(50).all()
    org_ids = {r.org_id for r in rows if r.org_id}
    orgs = {o.id: o.name for o in db.query(Organization).filter(Organization.id.in_(org_ids))} if org_ids else {}
    actor_ids = {r.actor_user_id for r in rows}
    actors = {u.id: u.name for u in db.query(User).filter(User.id.in_(actor_ids))} if actor_ids else {}
    return [
        AuditLogOut(
            id=r.id, org_id=r.org_id, org_name=orgs.get(r.org_id) if r.org_id else None,
            actor_name=actors.get(r.actor_user_id, "—"), action=r.action, detail=r.detail,
            created_at=r.created_at,
        )
        for r in rows
    ]
