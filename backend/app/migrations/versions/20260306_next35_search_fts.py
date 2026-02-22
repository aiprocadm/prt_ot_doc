"""next35 search fts/trgm improvements

Revision ID: 20260306_next35_search_fts
Revises: 20260305_next34_outbox_webhook_hardening
Create Date: 2026-03-06 00:00:00.000000
"""

from alembic import op


revision = "20260306_next35_search_fts"
down_revision = "20260305_next34_outbox_webhook_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_file_versions_filename_trgm ON file_versions USING GIN (filename gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_file_text_index_raw_text_trgm ON file_text_index USING GIN (raw_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_file_text_index_raw_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_file_versions_filename_trgm")
