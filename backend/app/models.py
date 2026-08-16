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
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="Awaiting assignment")
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


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
