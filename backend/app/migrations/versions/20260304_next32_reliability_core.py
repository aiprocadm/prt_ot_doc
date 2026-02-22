"""NEXT-32 reliability core infra.

Revision ID: 20260304_next32_reliability_core
Revises: 20260303_next30_approval_signing_core
Create Date: 2026-03-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260304_next32_reliability_core"
down_revision: Union[str, None] = "20260303_next30_approval_signing_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.add_column(sa.Column("response_headers", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "webhook_endpoints",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("secret", sa.String(length=512), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("subscribed_events", sa.JSON(), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_endpoint_tenant_enabled", "webhook_endpoints", ["tenant_id", "is_enabled"], unique=False)

    if op.get_bind().dialect.has_table(op.get_bind(), "webhook_delivery"):
        op.rename_table("webhook_delivery", "webhook_deliveries")

    with op.batch_alter_table("webhook_deliveries", schema=None) as batch:
        try:
            batch.drop_constraint("uq_webhook_delivery_subscription_event", type_="unique")
        except Exception:
            pass
        try:
            batch.alter_column("subscription_id", new_column_name="endpoint_id")
        except Exception:
            pass
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_response_body", sa.Text(), nullable=True))
        batch.create_unique_constraint("uq_webhook_delivery_endpoint_event", ["endpoint_id", "event_id"])


def downgrade() -> None:
    with op.batch_alter_table("webhook_deliveries", schema=None) as batch:
        batch.drop_constraint("uq_webhook_delivery_endpoint_event", type_="unique")
        batch.drop_column("last_response_body")
        batch.drop_column("next_attempt_at")
    op.rename_table("webhook_deliveries", "webhook_delivery")
    op.drop_index("ix_webhook_endpoint_tenant_enabled", table_name="webhook_endpoints")
    op.drop_table("webhook_endpoints")
    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.drop_column("expires_at")
        batch.drop_column("response_headers")
