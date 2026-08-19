"""requests + sku_rows: Platform Options batch/qualification/verification fields

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("exhibit_batch_start", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("exhibit_batch_end", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("tentative_approval_months", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("assembly_machine_qualification", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("assembly_qualification_qty", sa.Integer, nullable=True))
    op.add_column("requests", sa.Column("assembly_qualification_date", sa.Date, nullable=True))
    op.add_column("requests", sa.Column("platform_design_verification_request", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("sample_request", sa.Boolean, nullable=True))
    op.add_column("requests", sa.Column("sample_request_qty", sa.Integer, nullable=True))
    op.add_column("sku_rows", sa.Column("batch_size_l", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("sku_rows", "batch_size_l")
    op.drop_column("requests", "sample_request_qty")
    op.drop_column("requests", "sample_request")
    op.drop_column("requests", "platform_design_verification_request")
    op.drop_column("requests", "assembly_qualification_date")
    op.drop_column("requests", "assembly_qualification_qty")
    op.drop_column("requests", "assembly_machine_qualification")
    op.drop_column("requests", "tentative_approval_months")
    op.drop_column("requests", "exhibit_batch_end")
    op.drop_column("requests", "exhibit_batch_start")
