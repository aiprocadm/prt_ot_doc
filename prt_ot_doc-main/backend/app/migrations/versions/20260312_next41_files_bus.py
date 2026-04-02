"""next41 files bus and links

Revision ID: 20260312_next41
Revises: 20260311_next40_job_step_order_index
Create Date: 2026-03-12 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260312_next41"
down_revision = "20260311_next40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False, server_default="main"),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("av_vendor", sa.String(length=64), nullable=True),
        sa.Column("av_result_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "file_download_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("purpose", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_files_tenant_sha256", "files", ["tenant_id", "sha256"])
    op.create_index("ix_files_tenant_created_at", "files", ["tenant_id", "created_at"])
    op.create_index("ix_files_tenant_status", "files", ["tenant_id", "status"])
    op.create_index("ix_file_links_tenant_entity", "file_links", ["tenant_id", "entity_type", "entity_id"])
    op.create_index("ix_file_download_logs_tenant_file_created", "file_download_logs", ["tenant_id", "file_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_file_download_logs_tenant_file_created", table_name="file_download_logs")
    op.drop_index("ix_file_links_tenant_entity", table_name="file_links")
    op.drop_index("ix_files_tenant_status", table_name="files")
    op.drop_index("ix_files_tenant_created_at", table_name="files")
    op.drop_index("ix_files_tenant_sha256", table_name="files")
    op.drop_table("file_download_logs")
    op.drop_table("file_links")
    op.drop_table("files")
