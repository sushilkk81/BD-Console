"""initial: organizations, users, requests

Revision ID: 0001
Revises:
Create Date: 2026-08-15

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("domain", sa.String(200), nullable=False, unique=True),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("submitted_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("brand", sa.String(200), nullable=False),
        sa.Column("market", sa.String(50), nullable=False),
        sa.Column("device", sa.String(100), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="Awaiting assignment"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("requests")
    op.drop_table("users")
    op.drop_table("organizations")
