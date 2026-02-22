"""NEXT-23 pipeline orchestration v1

Revision ID: 20260227_next23
Revises: 20260226_next20
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260227_next23"
down_revision = "20260226_next20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_profiles",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("limits", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pipeline_profile_tenant_code"),
    )
    op.create_index("ix_pipeline_profiles_tenant_active", "pipeline_profiles", ["tenant_id", "is_active"])

    op.add_column("document_jobs", sa.Column("profile_id", sa.String(length=36), nullable=True))
    op.add_column("document_jobs", sa.Column("idempotency_key_id", sa.String(length=36), nullable=True))
    op.add_column("document_jobs", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_jobs", sa.Column("input", sa.JSON(), nullable=True))
    op.add_column("document_jobs", sa.Column("output", sa.JSON(), nullable=True))
    op.add_column("document_jobs", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_document_jobs_tenant_created", "document_jobs", ["tenant_id", "created_at"])

    op.add_column("document_job_steps", sa.Column("order", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("document_job_steps", sa.Column("input", sa.JSON(), nullable=True))
    op.add_column("document_job_steps", sa.Column("output", sa.JSON(), nullable=True))
    op.add_column("document_job_steps", sa.Column("logs_file_id", sa.String(length=36), nullable=True))
    op.add_column("document_job_steps", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_job_steps_tenant_job_order", "document_job_steps", ["tenant_id", "job_id", "order"])


def downgrade() -> None:
    op.drop_index("ix_job_steps_tenant_job_order", table_name="document_job_steps")
    op.drop_column("document_job_steps", "deleted_at")
    op.drop_column("document_job_steps", "logs_file_id")
    op.drop_column("document_job_steps", "output")
    op.drop_column("document_job_steps", "input")
    op.drop_column("document_job_steps", "order")

    op.drop_index("ix_document_jobs_tenant_created", table_name="document_jobs")
    op.drop_column("document_jobs", "deleted_at")
    op.drop_column("document_jobs", "output")
    op.drop_column("document_jobs", "input")
    op.drop_column("document_jobs", "attempts")
    op.drop_column("document_jobs", "idempotency_key_id")
    op.drop_column("document_jobs", "profile_id")

    op.drop_index("ix_pipeline_profiles_tenant_active", table_name="pipeline_profiles")
    op.drop_table("pipeline_profiles")
