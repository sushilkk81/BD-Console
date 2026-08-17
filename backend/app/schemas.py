import datetime as dt
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


CART_SIZES = ["1.5 mL", "3 mL", "1 mL PFS", "3 mL PFS", "1 mL Bespoke"]


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
    strengths: list[str] = []
    viscosity_val: Optional[float] = None
    device: Optional[str] = None
    differentiated: bool = False
    total: float = 0


class SkuRowIn(BaseModel):
    strength: str
    cartridge: str
    fill_ml: float

    @field_validator("cartridge")
    @classmethod
    def cartridge_must_be_known_size(cls, v: str) -> str:
        if v not in CART_SIZES:
            raise ValueError(f"cartridge must be one of {CART_SIZES}")
        return v

    @field_validator("fill_ml")
    @classmethod
    def fill_ml_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("fill_ml must be greater than 0")
        return v


class SkuRowOut(BaseModel):
    id: int
    strength: str
    cartridge: str
    fill_ml: float


class RequestStep1Update(BaseModel):
    brand: str
    market: str
    strengths: list[str]
    viscosity_val: Optional[float] = None
    device: Optional[str] = None
    differentiated: bool = False
    sku_rows: list[SkuRowIn]


class ServiceSelectionIn(BaseModel):
    sku_row_id: int
    standard_dv: bool = True
    threshold: bool = False
    ifu: bool = False
    human_factor: bool = False


class ServiceSelectionOut(BaseModel):
    id: int
    sku_row_id: int
    standard_dv: bool
    threshold: bool
    ifu: bool
    human_factor: bool


class ServicesUpdate(BaseModel):
    selections: list[ServiceSelectionIn]
    comment: Optional[str] = None
    urgency: Optional[str] = None


class SelectOptionRequest(BaseModel):
    chosen_option: int = Field(ge=1, le=3)


class PlatformOptionRow(BaseModel):
    sku: str
    cartridge: str
    platform: Optional[str] = None
    cls: Optional[str] = None
    sub: Optional[str] = None
    resolution: Optional[str] = None
    lockout: Optional[str] = None
    mech: Optional[str] = None
    band: str
    pct: Optional[int] = None
    fallback: bool
    visc_limited: bool


class PlatformOptionsOut(BaseModel):
    options: dict[str, list[PlatformOptionRow]]


class ReferenceProductOut(BaseModel):
    brand: str
    molecule: str
    device: str
    strengths: list[str]
    visc_val: float
    visc_ref: str
    cartridge: str


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
    viscosity_val: Optional[float] = None
    differentiated: bool = False
    chosen_option: Optional[int] = None
    severity: Optional[str] = None
    timeline_months: Optional[int] = None
    comment: Optional[str] = None
    urgency: Optional[str] = None


class RequestDetailOut(RequestOut):
    sku_rows: list[SkuRowOut] = []
    service_selections: list[ServiceSelectionOut] = []


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
