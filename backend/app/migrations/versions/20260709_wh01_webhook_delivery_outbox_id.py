"""webhook_deliveries.outbox_id link (#20).

Additive: nullable ``outbox_id`` on ``webhook_deliveries`` so the delivery :retry
endpoint can re-drive the source Outbox entry (the OutboxProcessor is the actual
delivery engine; this table is only a status mirror). No backfill, no enum.
Chains off wa09.

Revision ID: 20260709_wh01_webhook_delivery_outbox_id
Revises: 20260705_wa09_ppe_safety_budget
Create Date: 2026-07-09 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260709_wh01_webhook_delivery_outbox_id"
down_revision = "20260705_wa09_ppe_safety_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("webhook_deliveries", sa.Column("outbox_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("webhook_deliveries", "outbox_id")
