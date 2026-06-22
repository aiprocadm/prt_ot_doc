"""next15 document pipeline orchestrator fields

Revision ID: 20260223_next15
Revises: 20260222_next10
Create Date: 2026-02-23 00:00:00
"""

import sqlalchemy as sa
from alembic import op

revision = "20260223_next15"
down_revision = "20260222_next10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_jobs",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="pipeline"),
    )
    op.add_column("document_jobs", sa.Column("preset_id", sa.String(length=36), nullable=True))
    op.add_column(
        "document_jobs",
        sa.Column("input_sha256", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "document_jobs",
        sa.Column("request_hash", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "document_jobs",
        sa.Column("idempotency_key", sa.String(length=128), nullable=False, server_default=""),
    )
    op.add_column(
        "document_jobs",
        sa.Column("result_document_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "document_jobs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_document_jobs_tenant_idempotency", "document_jobs", ["tenant_id", "idempotency_key"]
    )

    op.add_column("document_job_steps", sa.Column("input_ref", sa.JSON(), nullable=True))
    op.add_column("document_job_steps", sa.Column("output_ref", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_job_steps", "output_ref")
    op.drop_column("document_job_steps", "input_ref")

    op.drop_index("ix_document_jobs_tenant_idempotency", table_name="document_jobs")
    op.drop_column("document_jobs", "cancel_requested_at")
    op.drop_column("document_jobs", "result_document_version_id")
    op.drop_column("document_jobs", "idempotency_key")
    op.drop_column("document_jobs", "request_hash")
    op.drop_column("document_jobs", "input_sha256")
    op.drop_column("document_jobs", "preset_id")
    op.drop_column("document_jobs", "kind")
