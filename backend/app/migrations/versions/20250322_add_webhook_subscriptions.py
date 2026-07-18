"""Add webhook subscriptions

Revision ID: 20250322_add_webhook_subscriptions
Revises: 20250321_outbox_dedupe_key
Create Date: 2025-03-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250322_add_webhook_subscriptions"
down_revision: Union[str, None] = "20250321_outbox_dedupe_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscription",
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_subscription_event_type",
        "webhook_subscription",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_subscription_tenant_event",
        "webhook_subscription",
        ["tenant_id", "event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_subscription_tenant_event", table_name="webhook_subscription")
    op.drop_index("ix_webhook_subscription_event_type", table_name="webhook_subscription")
    op.drop_table("webhook_subscription")
