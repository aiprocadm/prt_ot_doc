"""NEXT-39 job orchestrator + pipeline engine core

Revision ID: 20260310_next39
Revises: 20260308_next38
Create Date: 2026-03-10
"""

import sqlalchemy as sa
from alembic import op

revision = "20260310_next39"
down_revision = "20260308_next38_audit_chain_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "package_profiles",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("steps_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_package_profile_tenant_code"),
    )
    op.create_index("ix_package_profiles_tenant_code", "package_profiles", ["tenant_id", "code"])

    op.add_column("document_jobs", sa.Column("input_payload_json", sa.JSON(), nullable=True))
    op.add_column("document_jobs", sa.Column("output_payload_json", sa.JSON(), nullable=True))
    op.add_column(
        "document_jobs",
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_document_jobs_tenant_updated", "document_jobs", ["tenant_id", "updated_at"])

    op.add_column("document_job_steps", sa.Column("step_key", sa.String(length=64), nullable=True))
    op.add_column("document_job_steps", sa.Column("step_order", sa.Integer(), nullable=True))
    op.add_column("document_job_steps", sa.Column("logs_uri", sa.String(length=512), nullable=True))
    op.create_index("ix_job_steps_tenant_job", "document_job_steps", ["tenant_id", "job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_steps_tenant_job", table_name="document_job_steps")
    op.drop_column("document_job_steps", "logs_uri")
    op.drop_column("document_job_steps", "step_order")
    op.drop_column("document_job_steps", "step_key")

    op.drop_index("ix_document_jobs_tenant_updated", table_name="document_jobs")
    op.drop_column("document_jobs", "current_step_index")
    op.drop_column("document_jobs", "output_payload_json")
    op.drop_column("document_jobs", "input_payload_json")

    op.drop_index("ix_package_profiles_tenant_code", table_name="package_profiles")
    op.drop_table("package_profiles")
