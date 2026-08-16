import datetime as dt
from typing import Optional

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    name: str
    email: EmailStr
    role: Optional[str] = None  # required when email domain is shaily.com


class UserOut(BaseModel):
    id: int
    org_id: int
    name: str
    email: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RequestCreate(BaseModel):
    brand: str
    market: str
    device: Optional[str] = None
    total: float = 0


class RequestOut(BaseModel):
    id: int
    org_id: int
    org_name: str
    submitted_by: int
    brand: str
    market: str
    device: Optional[str]
    status: str
    total: float
    assigned_kam_id: Optional[int] = None
    assigned_kam_name: Optional[str] = None
    suggested_kam_id: Optional[int] = None
    suggested_kam_name: Optional[str] = None


class KamOut(BaseModel):
    id: int
    name: str
    email: str


class OrgKamMapOut(BaseModel):
    org_id: int
    org_name: str
    kam_user_id: Optional[int] = None
    kam_name: Optional[str] = None


class OrgKamMapUpdate(BaseModel):
    kam_user_id: int


class AssignKamRequest(BaseModel):
    kam_user_id: int


class DashboardLive(BaseModel):
    requests_by_status: dict[str, int]
    total_requests: int


class DashboardMetricsOut(BaseModel):
    quarterly_target: dict
    new_customers_qtr: dict
    platform_production: dict
    rep_quarterly: dict
    rep_platform_matrix: dict
    rep_customer_matrix: dict
    live: DashboardLive


class AuditLogOut(BaseModel):
    id: int
    org_id: Optional[int]
    org_name: Optional[str] = None
    actor_name: str
    action: str
    detail: str
    created_at: dt.datetime
