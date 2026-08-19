"""reference_products: viscosity range + multi-citation columns

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reference_products", sa.Column("visc_val_low", sa.Numeric(6, 2), nullable=True))
    op.add_column("reference_products", sa.Column("visc_val_high", sa.Numeric(6, 2), nullable=True))
    op.add_column(
        "reference_products",
        sa.Column("visc_citations", sa.JSON, nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("reference_products", "visc_citations")
    op.drop_column("reference_products", "visc_val_high")
    op.drop_column("reference_products", "visc_val_low")
