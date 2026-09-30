"""molecule_source_observations: retrieval provenance separate from publication

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29

source_url remains the publisher's canonical URL. These columns record how the bytes
were actually obtained, so a CMS file fetched from a web archive is stored as an
archived publication with its archive URL, capture date and checksum — never as live
publisher access.

"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("molecule_source_observations",
                  sa.Column("provenance_class", sa.String(40), nullable=False,
                            server_default="user_supplied_file"))
    op.add_column("molecule_source_observations",
                  sa.Column("retrieval_url", sa.Text, nullable=True))
    op.add_column("molecule_source_observations",
                  sa.Column("archive_capture_date", sa.DateTime(timezone=True), nullable=True))
    op.add_column("molecule_source_observations",
                  sa.Column("content_sha256", sa.String(64), nullable=True))
    op.add_column("molecule_source_observations",
                  sa.Column("file_verification", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("molecule_source_observations", "file_verification")
    op.drop_column("molecule_source_observations", "content_sha256")
    op.drop_column("molecule_source_observations", "archive_capture_date")
    op.drop_column("molecule_source_observations", "retrieval_url")
    op.drop_column("molecule_source_observations", "provenance_class")
