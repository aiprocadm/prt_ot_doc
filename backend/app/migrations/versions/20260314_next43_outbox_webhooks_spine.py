"""next43 outbox/webhook spine hardening

Revision ID: 20260314_next43_outbox_webhooks_spine
Revises: 20260313_next42_rbac_abac_audit
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260314_next43_outbox_webhooks_spine"
down_revision = "20260313_next42_rbac_abac_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch:
        batch.add_column(sa.Column("aggregate_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("aggregate_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("headers", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE outbox_events SET aggregate_type = 'unknown' WHERE aggregate_type IS NULL")

    with op.batch_alter_table("outbox_events") as batch:
        batch.alter_column("aggregate_type", existing_type=sa.String(length=64), nullable=False)
        batch.drop_constraint("uq_outbox_event_tenant_event", type_="unique")
        batch.create_unique_constraint("uq_outbox_event_event", ["event_id"])
        batch.drop_index("ix_outbox_events_status_next_attempt")
        batch.create_index(
            "ix_outbox_events_status_next_created",
            ["status", "next_attempt_at", "created_at"],
            unique=False,
        )
        batch.create_index(
            "ix_outbox_events_aggregate",
            ["aggregate_type", "aggregate_id", "created_at"],
            unique=False,
        )

    op.create_table(
        "webhook_subscriptions",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    with op.batch_alter_table("webhook_deliveries") as batch:
        batch.add_column(sa.Column("subscription_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("status_code", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("response_body", sa.Text(), nullable=True))
        batch.add_column(sa.Column("error", sa.Text(), nullable=True))

    op.create_index(
        "ix_webhook_deliveries_tenant_subscription_delivered",
        "webhook_deliveries",
        ["tenant_id", "subscription_id", "delivered_at"],
        unique=False,
    )

    op.create_table(
        "inbound_webhook_dedup",
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "source", "dedup_key", name="uq_inbound_webhook_dedup"),
    )


def downgrade() -> None:
    op.drop_table("inbound_webhook_dedup")
    op.drop_index(
        "ix_webhook_deliveries_tenant_subscription_delivered", table_name="webhook_deliveries"
    )
    with op.batch_alter_table("webhook_deliveries") as batch:
        batch.drop_column("error")
        batch.drop_column("response_body")
        batch.drop_column("status_code")
        batch.drop_column("subscription_id")

    op.drop_table("webhook_subscriptions")

    with op.batch_alter_table("outbox_events") as batch:
        batch.drop_index("ix_outbox_events_aggregate")
        batch.drop_index("ix_outbox_events_status_next_created")
        batch.create_index(
            "ix_outbox_events_status_next_attempt", ["status", "next_attempt_at"], unique=False
        )
        batch.drop_constraint("uq_outbox_event_event", type_="unique")
        batch.create_unique_constraint("uq_outbox_event_tenant_event", ["tenant_id", "event_id"])
        batch.drop_column("sent_at")
        batch.drop_column("headers")
        batch.drop_column("aggregate_id")
        batch.drop_column("aggregate_type")
