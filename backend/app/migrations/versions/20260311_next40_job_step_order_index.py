"""NEXT-40 align document_job_steps order index with step_order

Revision ID: 20260311_next40
Revises: 20260310_next39
Create Date: 2026-03-11
"""

from alembic import op

revision = "20260311_next40"
down_revision = "20260310_next39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_job_steps_tenant_job_order", table_name="document_job_steps")
    op.create_index("ix_job_steps_tenant_job_order", "document_job_steps", ["tenant_id", "job_id", "step_order"])


def downgrade() -> None:
    op.drop_index("ix_job_steps_tenant_job_order", table_name="document_job_steps")
    op.create_index("ix_job_steps_tenant_job_order", "document_job_steps", ["tenant_id", "job_id", "order"])
