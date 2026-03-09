"""next21 pdf conversion runs and file versions

Revision ID: 20260222_next21
Revises: 20260223_next15
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260222_next21"
down_revision = "20260223_next15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("app_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_file_versions_tenant_sha256", "file_versions", ["tenant_id", "sha256"])
    op.create_index("ix_file_versions_tenant_updated", "file_versions", ["tenant_id", "updated_at"])

    op.create_table(
        "pdf_conversion_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_file_id", sa.String(length=36), nullable=False),
        sa.Column("output_file_id", sa.String(length=36), nullable=True),
        sa.Column("source_document_version_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["input_file_id"], ["file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pdf_runs_tenant_status", "pdf_conversion_runs", ["tenant_id", "status"])
    op.create_index("ix_pdf_runs_input", "pdf_conversion_runs", ["tenant_id", "input_file_id"])


def downgrade() -> None:
    op.drop_index("ix_pdf_runs_input", table_name="pdf_conversion_runs")
    op.drop_index("ix_pdf_runs_tenant_status", table_name="pdf_conversion_runs")
    op.drop_table("pdf_conversion_runs")
    op.drop_index("ix_file_versions_tenant_updated", table_name="file_versions")
    op.drop_index("ix_file_versions_tenant_sha256", table_name="file_versions")
    op.drop_table("file_versions")
