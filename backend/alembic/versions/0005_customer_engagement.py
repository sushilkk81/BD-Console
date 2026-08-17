"""Customer engagement tracking: users.title, customer_visits, notifications

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("title", sa.String(50), nullable=True))

    op.create_table(
        "customer_visits",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False, unique=True),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(50), nullable=False),
        sa.Column("contact_title", sa.String(50), nullable=False),
        sa.Column("org_name", sa.String(200), nullable=False),
        sa.Column("pages_visited", sa.JSON, nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("recipient_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_visit_id", sa.Integer, sa.ForeignKey("customer_visits.id"), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("link_path", sa.String(200), nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("customer_visits")
    op.drop_column("users", "title")
