"""BD Manager & KAM dashboards: assigned_kam_id, org_kam_map, audit_log, dashboard_metrics

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("assigned_kam_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True))

    op.create_table(
        "org_kam_map",
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), primary_key=True),
        sa.Column("kam_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    op.create_table(
        "dashboard_metrics",
        sa.Column("key", sa.String(50), primary_key=True),
        sa.Column("payload", sa.JSON, nullable=False),
    )

    metrics = sa.table("dashboard_metrics", sa.column("key", sa.String), sa.column("payload", sa.JSON))
    op.bulk_insert(metrics, [
        {"key": "quarterly_target", "payload": {"Q1": 32, "Q2": 36, "Q3": 42, "Q4": 48}},
        {"key": "new_customers_qtr", "payload": {"Q1": 2, "Q2": 1, "Q3": 3, "Q4": 2}},
        {"key": "platform_production", "payload": {
            "Toby": 21, "Neo": 34, "Harmony": 18, "Axiom": 12, "Axiom Max": 9,
            "Protean": 15, "Tristan": 7, "Mira": 4, "Safe-LAN": 6,
        }},
        {"key": "rep_quarterly", "payload": {
            "Mr. MAH": {"region": "India", "quarters": {"Q1": 8, "Q2": 10, "Q3": 9, "Q4": 12}},
            "Mr. HEN": {"region": "Europe", "quarters": {"Q1": 6, "Q2": 7, "Q3": 8, "Q4": 9}},
            "Mr. MUK": {"region": "Asia", "quarters": {"Q1": 5, "Q2": 6, "Q3": 7, "Q4": 8}},
            "Mr. FED": {"region": "North America", "quarters": {"Q1": 7, "Q2": 6, "Q3": 9, "Q4": 10}},
            "Ms. SUK": {"region": "Europe", "quarters": {"Q1": 4, "Q2": 5, "Q3": 6, "Q4": 7}},
        }},
        {"key": "rep_platform_matrix", "payload": {
            "Mr. MAH": {"Neo": 12, "Toby": 11},
            "Mr. HEN": {"Harmony": 9, "Axiom": 9},
            "Mr. MUK": {"Protean": 8, "Axiom Max": 6},
            "Mr. FED": {"Toby": 10, "Tristan": 10},
            "Ms. SUK": {"Mira": 7, "Safe-LAN": 7},
        }},
        {"key": "rep_customer_matrix", "payload": {
            "Mr. MAH": {"Auro": 14, "McD": 9},
            "Mr. HEN": {"DRL": 11, "Chem": 7},
            "Mr. MUK": {"Sand": 8, "Torr": 6},
            "Mr. FED": {"Dem": 12, "Homo": 8},
            "Ms. SUK": {"Shun": 9, "Chem": 5},
        }},
    ])


def downgrade() -> None:
    op.drop_table("dashboard_metrics")
    op.drop_table("audit_log")
    op.drop_table("org_kam_map")
    op.drop_column("requests", "assigned_kam_id")
