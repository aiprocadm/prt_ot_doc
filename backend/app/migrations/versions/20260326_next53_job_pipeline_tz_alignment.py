"""next53 job pipeline orchestration tz alignment

Revision ID: 20260326_next53
Revises: 20260325_next52
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_next53"
down_revision = "20260325_next52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_jobs", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("document_job_steps", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column(
        "document_job_steps",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("document_job_steps", sa.Column("logs_ref", sa.String(length=512), nullable=True))

    op.execute("UPDATE document_job_steps SET seq = COALESCE(step_order, \"order\") WHERE seq IS NULL")
    op.execute("UPDATE document_job_steps SET attempt = COALESCE(attempts, 0) WHERE attempt = 0")

    op.create_index("ix_document_job_steps_job_seq", "document_job_steps", ["job_id", "seq"])
    op.create_index("ix_document_job_steps_job_status", "document_job_steps", ["job_id", "status"])

    op.add_column("pipeline_profiles", sa.Column("concurrency_limit_per_tenant", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_profiles", "concurrency_limit_per_tenant")

    op.drop_index("ix_document_job_steps_job_status", table_name="document_job_steps")
    op.drop_index("ix_document_job_steps_job_seq", table_name="document_job_steps")

    op.drop_column("document_job_steps", "logs_ref")
    op.drop_column("document_job_steps", "attempt")
    op.drop_column("document_job_steps", "seq")

    op.drop_column("document_jobs", "queued_at")
