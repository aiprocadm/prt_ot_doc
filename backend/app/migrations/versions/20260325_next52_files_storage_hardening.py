"""next52 files storage hardening

Revision ID: 20260325_next52
Revises: 20260320_next49_pipeline_lowcode_builder
Create Date: 2026-03-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260325_next52"
down_revision = "20260320_next49"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("files", sa.Column("original_name", sa.String(length=255), nullable=True))
    op.execute("UPDATE files SET original_name = original_filename WHERE original_name IS NULL")

    op.create_table(
        "file_scan_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False, server_default="clamav"),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("signature", sa.String(length=255), nullable=True),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_file_scan_results_file_scanned", "file_scan_results", ["file_id", "scanned_at"])


def downgrade() -> None:
    op.drop_index("ix_file_scan_results_file_scanned", table_name="file_scan_results")
    op.drop_table("file_scan_results")
    op.drop_column("files", "original_name")
    op.drop_column("files", "is_public")
