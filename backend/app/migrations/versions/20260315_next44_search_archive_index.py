"""next44 search archive content index

Revision ID: 20260315_next44_search_archive_index
Revises: 20260314_next43_outbox_webhooks_spine
Create Date: 2026-03-15 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260315_next44_search_archive_index"
down_revision = "20260314_next43_outbox_webhooks_spine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "file_content_index",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("doc_id", sa.String(length=36), nullable=True),
        sa.Column("content_text", postgresql.TSVECTOR(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="ru"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_id", name="uq_file_content_index_file_id"),
    )
    op.create_index(
        "ix_file_content_index_status_updated",
        "file_content_index",
        ["status", "updated_at"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX ix_file_content_index_content_text_gin ON file_content_index USING GIN (content_text)"
    )


def downgrade() -> None:
    op.drop_index("ix_file_content_index_content_text_gin", table_name="file_content_index")
    op.drop_index("ix_file_content_index_status_updated", table_name="file_content_index")
    op.drop_table("file_content_index")
