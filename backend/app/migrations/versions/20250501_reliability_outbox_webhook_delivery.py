"""Reliability primitives for webhook delivery tracking.

Revision ID: 20250501_reliability_outbox_webhook_delivery
Revises: 20250430_client_portal_packages_mvp
Create Date: 2025-05-01 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250501_reliability_outbox_webhook_delivery"
down_revision: Union[str, None] = "20250430_client_portal_packages_mvp"
branch_labels: Union[str, Sequence[str], None] = None
# Cross-branch dependency: upgrade() runs `op.batch_alter_table("webhook_subscription")`
# which requires the table created by 20250322_add_webhook_subscriptions. That migration
# lives on a separate Alembic branch that only merges with this branch at
# 20260416_next69_merge_heads (≈11 months later). Without an explicit depends_on,
# Alembic's topological ordering can run this migration before 20250322, producing
# `UndefinedTableError: relation "webhook_subscription" does not exist` on Postgres.
depends_on: Union[str, Sequence[str], None] = "20250322_add_webhook_subscriptions"


def upgrade() -> None:
    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.drop_constraint("uq_idempotency_key_per_tenant", type_="unique")

    with op.batch_alter_table("webhook_subscription", schema=None) as batch:
        batch.add_column(sa.Column("secret", sa.String(length=512), nullable=True))

    op.create_table(
        "webhook_delivery",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.JSON(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", "event_id", name="uq_webhook_delivery_subscription_event"),
    )
    op.create_index(
        "ix_webhook_delivery_lookup",
        "webhook_delivery",
        ["tenant_id", "subscription_id", "event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_lookup", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")

    with op.batch_alter_table("webhook_subscription", schema=None) as batch:
        batch.drop_column("secret")

    with op.batch_alter_table("idempotency_keys", schema=None) as batch:
        batch.create_unique_constraint("uq_idempotency_key_per_tenant", ["tenant_id", "key"])
