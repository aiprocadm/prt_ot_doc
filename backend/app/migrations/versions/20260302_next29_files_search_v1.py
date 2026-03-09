"""next29 files/search v1

Revision ID: 20260302_next29
Revises: 20260301_next26_pipeline_idempotency
Create Date: 2026-03-02 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260302_next29"
down_revision = "20260301_next26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("owner_entity_type", sa.String(length=64), nullable=False),
        sa.Column("owner_entity_id", sa.String(length=64), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("av_status", sa.String(length=32), nullable=False),
        sa.Column("text_index_status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "download_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("version_id", sa.String(length=36), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_text_index",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_version_id", sa.String(length=36), nullable=False),
        sa.Column("content_tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("lang", sa.String(length=16), nullable=False, server_default="simple"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_versions_tenant_status_updated", "file_versions", ["tenant_id", "status", "updated_at"])
    op.create_index("ix_file_objects_owner", "file_objects", ["tenant_id", "owner_entity_type", "owner_entity_id"])
    op.execute("CREATE INDEX ix_file_text_index_content_tsv ON file_text_index USING GIN (content_tsv)")


def downgrade() -> None:
    op.drop_index("ix_file_text_index_content_tsv", table_name="file_text_index")
    op.drop_index("ix_file_objects_owner", table_name="file_objects")
    op.drop_index("ix_file_versions_tenant_status_updated", table_name="file_versions")
    op.drop_table("file_text_index")
    op.drop_table("download_logs")
    op.drop_table("file_versions")
    op.drop_table("file_objects")
