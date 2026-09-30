"""CMS release registry and recurring metadata checks

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-29

Lets a new CMS release enter a documented validation workflow instead of requiring a
hardcoded digest edit, and records each metadata check so freshness can degrade to
unknown/stale rather than claiming "current" indefinitely.

"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cms_dataset_releases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("dataset_uuid", sa.String(100), nullable=True),
        sa.Column("publication_url", sa.Text, nullable=False),
        sa.Column("release_label", sa.String(200), nullable=True),
        sa.Column("data_year", sa.Integer, nullable=False),
        sa.Column("published_on", sa.Date, nullable=True),
        # Identifies a file. Does NOT verify the source — validation_status does that.
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("resolved_columns", sa.JSON, nullable=True),
        sa.Column("provenance_class", sa.String(40), nullable=False),
        sa.Column("retrieval_url", sa.Text, nullable=True),
        sa.Column("archive_capture_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("validation_report", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("source_kind", "data_year", "content_sha256",
                            name="uq_cdr_source_year_digest"),
    )
    op.create_index("ix_cdr_active", "cms_dataset_releases", ["source_kind", "is_active"])

    op.create_table(
        "cms_metadata_checks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metadata_url", sa.Text, nullable=True),
        sa.Column("latest_data_year_seen", sa.Integer, nullable=True),
        sa.Column("latest_release_label", sa.String(200), nullable=True),
        sa.Column("published_on_seen", sa.Date, nullable=True),
        sa.Column("new_release_detected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("raw_metadata", sa.JSON, nullable=True),
    )
    op.create_index("ix_cmc_checked_at", "cms_metadata_checks", ["source_kind", "checked_at"])


def downgrade() -> None:
    op.drop_index("ix_cmc_checked_at", table_name="cms_metadata_checks")
    op.drop_table("cms_metadata_checks")
    op.drop_index("ix_cdr_active", table_name="cms_dataset_releases")
    op.drop_table("cms_dataset_releases")
