"""next46 content search + global archive index

Revision ID: 20260317_next46_content_search_archive
Revises: 20260316_next45_notifications_autotasks_calendar
Create Date: 2026-03-17 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260317_next46_content_search_archive"
down_revision = "20260316_next45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=32), nullable=False, server_default="russian"),
        sa.Column("fts", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_file_id", sa.String(length=36), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["source_file_id"], ["files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_documents_tenant_entity",
        "search_documents",
        ["tenant_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_search_documents_tenant_updated",
        "search_documents",
        ["tenant_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_search_documents_source_file",
        "search_documents",
        ["tenant_id", "source_file_id"],
        unique=False,
    )
    op.execute("CREATE INDEX ix_search_documents_fts_gin ON search_documents USING GIN (fts)")
    op.execute("CREATE INDEX ix_search_documents_meta_gin ON search_documents USING GIN (meta)")


def downgrade() -> None:
    op.drop_index("ix_search_documents_meta_gin", table_name="search_documents")
    op.drop_index("ix_search_documents_fts_gin", table_name="search_documents")
    op.drop_index("ix_search_documents_source_file", table_name="search_documents")
    op.drop_index("ix_search_documents_tenant_updated", table_name="search_documents")
    op.drop_index("ix_search_documents_tenant_entity", table_name="search_documents")
    op.drop_table("search_documents")
