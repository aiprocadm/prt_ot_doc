"""Add user attributes table for ABAC contexts

Revision ID: 20260221_next7_user_attributes
Revises: 20250601_tenant_quotas_and_counters
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260221_next7_user_attributes"
down_revision = "20250601_tenant_quotas_and_counters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_attribute",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("company_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("site_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("project_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("contractor_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_user_attribute"),
    )
    op.create_index("ix_user_attribute_user", "user_attribute", ["tenant_id", "user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_attribute_user", table_name="user_attribute")
    op.drop_table("user_attribute")
