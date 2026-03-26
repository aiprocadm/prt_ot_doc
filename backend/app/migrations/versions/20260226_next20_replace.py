"""NEXT-20 replace maps and runs

Revision ID: 20260226_next20
Revises: 20260225_next19
Create Date: 2026-02-26
"""

import sqlalchemy as sa
from alembic import op

revision = "20260226_next20"
down_revision = "20260225_next19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replace_map",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False, server_default="inline"),
        sa.Column("rules", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("exclusions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_replace_map_tenant_code"),
    )
    op.create_index("ix_replace_map_tenant_code", "replace_map", ["tenant_id", "code"])
    op.create_index("ix_replace_map_updated_at", "replace_map", ["updated_at"])

    op.create_table(
        "replace_run",
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("replace_map_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("report_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("before_file_id", sa.String(length=512), nullable=False),
        sa.Column("after_file_id", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_replace_run_tenant_created", "replace_run", ["tenant_id", "created_at"])
    op.create_index("ix_replace_run_document", "replace_run", ["tenant_id", "document_version_id"])


def downgrade() -> None:
    op.drop_index("ix_replace_run_document", table_name="replace_run")
    op.drop_index("ix_replace_run_tenant_created", table_name="replace_run")
    op.drop_table("replace_run")
    op.drop_index("ix_replace_map_updated_at", table_name="replace_map")
    op.drop_index("ix_replace_map_tenant_code", table_name="replace_map")
    op.drop_table("replace_map")
