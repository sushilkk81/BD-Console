import datetime as dt
from typing import Optional

from sqlalchemy import ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "internal" | "customer"
    domain: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)

    users: Mapped[list["User"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="users")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_kam_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    brand: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(50), nullable=False)
    device: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Draft")
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    viscosity_val: Mapped[Optional[float]] = mapped_column(Numeric(6, 2), nullable=True)
    differentiated: Mapped[bool] = mapped_column(nullable=False, default=False)
    chosen_option: Mapped[Optional[int]] = mapped_column(nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    timeline_months: Mapped[Optional[int]] = mapped_column(nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    urgency: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    sku_rows: Mapped[list["SkuRow"]] = relationship(back_populates="request", order_by="SkuRow.id")


class OrgKamMap(Base):
    __tablename__ = "org_kam_map"

    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    kam_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class DashboardMetric(Base):
    __tablename__ = "dashboard_metrics"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class SkuRow(Base):
    __tablename__ = "sku_rows"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    strength: Mapped[str] = mapped_column(String(50), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    fill_ml: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)

    request: Mapped["Request"] = relationship(back_populates="sku_rows")
    service_selections: Mapped[list["ServiceSelection"]] = relationship(back_populates="sku_row")


class ServiceSelection(Base):
    __tablename__ = "service_selections"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_row_id: Mapped[int] = mapped_column(ForeignKey("sku_rows.id"), nullable=False)
    standard_dv: Mapped[bool] = mapped_column(nullable=False, default=True)
    threshold: Mapped[bool] = mapped_column(nullable=False, default=False)
    ifu: Mapped[bool] = mapped_column(nullable=False, default=False)
    human_factor: Mapped[bool] = mapped_column(nullable=False, default=False)

    sku_row: Mapped["SkuRow"] = relationship(back_populates="service_selections")


class ReferenceProduct(Base):
    __tablename__ = "reference_products"

    brand: Mapped[str] = mapped_column(String(100), primary_key=True)
    molecule: Mapped[str] = mapped_column(String(200), nullable=False)
    device: Mapped[str] = mapped_column(String(100), nullable=False)
    dose: Mapped[str] = mapped_column(String(20), nullable=False)
    visc: Mapped[str] = mapped_column(String(20), nullable=False)
    visc_val: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    cartridge: Mapped[str] = mapped_column(String(50), nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False)
    visc_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    mech_drive: Mapped[str] = mapped_column(String(50), nullable=False)
    mech_dose: Mapped[str] = mapped_column(String(20), nullable=False)
    mech_label: Mapped[str] = mapped_column(String(200), nullable=False)
    ob_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    ob_claims: Mapped[list] = mapped_column(JSON, nullable=False)
    presentations: Mapped[dict] = mapped_column(JSON, nullable=False)
    presentations_ref: Mapped[str] = mapped_column(String(300), nullable=False, default="")


class ReferenceProductMarket(Base):
    __tablename__ = "reference_product_markets"

    brand: Mapped[str] = mapped_column(ForeignKey("reference_products.brand"), primary_key=True)
    market: Mapped[str] = mapped_column(String(50), primary_key=True)
    device: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    mech_drive: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mech_dose: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    mech_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    ob_ref: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    ob_claims: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    market_note: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    presentations: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pres_ref: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)


class PlatformSheet(Base):
    __tablename__ = "platform_sheet"

    variant: Mapped[str] = mapped_column(String(100), primary_key=True)
    family: Mapped[str] = mapped_column(String(100), nullable=False)
    cls: Mapped[str] = mapped_column(String(50), nullable=False)
    sub: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    resolution: Mapped[str] = mapped_column(String(200), nullable=False)
    lockout: Mapped[str] = mapped_column(String(10), nullable=False)
    carts: Mapped[list] = mapped_column(JSON, nullable=False)
    mech: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(10), nullable=False)
    moderate: Mapped[bool] = mapped_column(nullable=False, default=False)


class ServicePricing(Base):
    __tablename__ = "service_pricing"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
