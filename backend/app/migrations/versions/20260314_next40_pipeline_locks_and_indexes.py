"""next40 pipeline locks and job indexes

Revision ID: 20260314_next40
Revises: 20260310_next39
Create Date: 2026-03-14 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260314_next40"
down_revision = "20260310_next39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_step_locks",
        sa.Column("running_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_pipeline_step_locks_tenant"),
    )
    op.create_index("ix_pipeline_step_locks_tenant_updated", "pipeline_step_locks", ["tenant_id", "updated_at"], unique=False)

    op.create_index("ix_document_jobs_status_updated", "document_jobs", ["status", "updated_at"], unique=False)
    op.create_index("ix_document_jobs_created_at", "document_jobs", ["created_at"], unique=False)
    op.create_index("ix_document_jobs_idempotency_key", "document_jobs", ["idempotency_key"], unique=False)
    op.create_index("ix_document_job_steps_job_status", "document_job_steps", ["job_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_document_job_steps_job_status", table_name="document_job_steps")
    op.drop_index("ix_document_jobs_idempotency_key", table_name="document_jobs")
    op.drop_index("ix_document_jobs_created_at", table_name="document_jobs")
    op.drop_index("ix_document_jobs_status_updated", table_name="document_jobs")

    op.drop_index("ix_pipeline_step_locks_tenant_updated", table_name="pipeline_step_locks")
    op.drop_table("pipeline_step_locks")
