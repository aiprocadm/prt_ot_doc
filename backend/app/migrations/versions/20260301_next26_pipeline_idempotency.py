"""NEXT-26 idempotency + job logs + step retries

Revision ID: 20260301_next26
Revises: 20260227_next23
Create Date: 2026-03-01
"""

from alembic import op
import sqlalchemy as sa


revision = "20260301_next26"
down_revision = "20260227_next23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_job_steps", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("document_job_steps", sa.Column("inputs_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_document_job_steps_status", "document_job_steps", ["status"])
    op.create_index("ix_document_job_steps_job_step", "document_job_steps", ["job_id", "step_code"])

    op.create_table(
        "job_logs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("step_code", sa.String(length=64), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=1024), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["document_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_logs_tenant_job_created", "job_logs", ["tenant_id", "job_id", "created_at"])

    op.add_column("idempotency_keys", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_column("idempotency_keys", "last_seen_at")

    op.drop_index("ix_job_logs_tenant_job_created", table_name="job_logs")
    op.drop_table("job_logs")

    op.drop_index("ix_document_job_steps_job_step", table_name="document_job_steps")
    op.drop_index("ix_document_job_steps_status", table_name="document_job_steps")
    op.drop_column("document_job_steps", "inputs_hash")
    op.drop_column("document_job_steps", "max_attempts")
