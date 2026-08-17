"""KAM assessment fields and request_messages thread table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("kam_cost_usd", sa.Numeric(12, 2), nullable=True))
    op.add_column("requests", sa.Column("kam_timeline_months", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("kam_notes", sa.Text, nullable=True))

    op.create_table(
        "request_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("sender_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("request_messages")
    op.drop_column("requests", "kam_notes")
    op.drop_column("requests", "kam_timeline_months")
    op.drop_column("requests", "kam_cost_usd")
