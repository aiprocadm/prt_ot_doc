"""NEXT-11 tenancy control-plane settings and quota extensions.

Revision ID: 20260221_next11_tenancy_control_plane
Revises: 20260222_next10
Create Date: 2026-02-21 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260221_next11_tenancy_control_plane"
down_revision: Union[str, None] = "20260222_next10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenant", sa.Column("s3_prefix", sa.String(length=255), nullable=True))
    op.execute("UPDATE tenant SET s3_prefix = id WHERE s3_prefix IS NULL")

    op.create_table(
        "tenant_settings",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("schema_name", sa.String(length=128), nullable=False),
        sa.Column("s3_prefix", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=True),
        sa.Column("retention_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("integration_keys", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schema_name"),
        sa.UniqueConstraint("tenant_id"),
    )
    op.execute(
        """
        INSERT INTO tenant_settings (id, tenant_id, schema_name, s3_prefix, retention_policy, integration_keys, created_at, updated_at, version)
        SELECT id || '-cfg', id, schema_name, s3_prefix, '{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
        FROM tenant
        """
    )

    op.add_column("tenant_quotas", sa.Column("monthly_edo_outgoing", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("tenant_quotas", sa.Column("enforce_billing_gate", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("tenant_quotas", "enforce_billing_gate")
    op.drop_column("tenant_quotas", "monthly_edo_outgoing")
    op.drop_table("tenant_settings")
    op.drop_column("tenant", "s3_prefix")
