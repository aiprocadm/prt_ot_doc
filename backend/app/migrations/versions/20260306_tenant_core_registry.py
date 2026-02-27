"""tenant core registry tables

Revision ID: 20260306_tenant_core_registry
Revises: 20260221_next11_tenancy_control_plane
Create Date: 2026-03-06 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "20260306_tenant_core_registry"
down_revision: str | None = "20260221_next11_tenancy_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_integrations_keys",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_tenant_integrations_keys_tenant_provider"),
    )
    op.create_index("ix_tenant_integrations_keys_tenant_id", "tenant_integrations_keys", ["tenant_id"])

    op.create_table(
        "tenant_quotas_counters",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("counter_name", sa.String(length=64), nullable=False),
        sa.Column("period", sa.String(length=7), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "counter_name", "period", name="uq_tenant_quota_counter"),
    )
    op.create_index("ix_tenant_quotas_counters_tenant_id", "tenant_quotas_counters", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_quotas_counters_tenant_id", table_name="tenant_quotas_counters")
    op.drop_table("tenant_quotas_counters")
    op.drop_index("ix_tenant_integrations_keys_tenant_id", table_name="tenant_integrations_keys")
    op.drop_table("tenant_integrations_keys")
