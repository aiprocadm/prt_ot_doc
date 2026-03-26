"""next50 tenant limits, billing events and subscription extensions

Revision ID: 20260321_next50_tenant_limits_billing_events
Revises: 20260320_next49_pipeline_lowcode_builder
Create Date: 2026-03-21 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260321_next50_tenant_limits_billing_events"
down_revision = "20260320_next49"
branch_labels = None
depends_on = None

billing_event_type = sa.Enum(
    "generation_completed",
    "edo_sent",
    "file_uploaded",
    "worker_activated",
    "plan_changed",
    "payment_failed",
    "payment_succeeded",
    name="billingeventtype",
)


def upgrade() -> None:
    billing_event_type.create(op.get_bind(), checkfirst=True)
    op.add_column("subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("subscriptions", sa.Column("external_customer_id", sa.String(length=128), nullable=True))
    op.create_table(
        "tenant_rate_limits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("concurrency_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("burst", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("rps", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("queues", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_rate_limits_tenant"),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("type", billing_event_type, nullable=False),
        sa.Column("ref_type", sa.String(length=64), nullable=True),
        sa.Column("ref_id", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "type", "ref_type", "ref_id", name="uq_billing_event_dedup"),
    )
    op.create_index("ix_billing_events_tenant_created", "billing_events", ["tenant_id", "created_at"], unique=False)
    op.create_index("ix_billing_events_type", "billing_events", ["type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_billing_events_type", table_name="billing_events")
    op.drop_index("ix_billing_events_tenant_created", table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_table("tenant_rate_limits")
    op.drop_column("subscriptions", "external_customer_id")
    op.drop_column("subscriptions", "cancel_at_period_end")
    billing_event_type.drop(op.get_bind(), checkfirst=True)
