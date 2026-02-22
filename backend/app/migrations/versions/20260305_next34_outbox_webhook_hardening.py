"""NEXT-34 outbox and webhook delivery hardening.

Revision ID: 20260305_next34_outbox_webhook_hardening
Revises: 20260304_next32_reliability_core
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260305_next34_outbox_webhook_hardening"
down_revision: Union[str, None] = "20260304_next32_reliability_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("webhook_endpoints", schema=None) as batch:
        batch.add_column(sa.Column("name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="5000"))

    with op.batch_alter_table("webhook_deliveries", schema=None) as batch:
        batch.add_column(sa.Column("request_headers", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("response_headers", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("webhook_deliveries", schema=None) as batch:
        batch.drop_column("latency_ms")
        batch.drop_column("ended_at")
        batch.drop_column("started_at")
        batch.drop_column("response_headers")
        batch.drop_column("request_headers")

    with op.batch_alter_table("webhook_endpoints", schema=None) as batch:
        batch.drop_column("timeout_ms")
        batch.drop_column("name")
