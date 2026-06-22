"""Reliability primitives for webhook delivery tracking.

Revision ID: 20250501_reliability_outbox_webhook_delivery
Revises: (20250430_client_portal_packages_mvp, 20250322_add_webhook_subscriptions)
Create Date: 2025-05-01 00:00:00.000000

History:
* iter-10 (PR #559) added ``depends_on = "20250322_add_webhook_subscriptions"``
  to fix a cross-branch UndefinedTableError on Postgres
  (``webhook_subscription`` table didn't exist when this migration's
  ``batch_alter_table`` ran).
* iter-15f attempted to drop 20250322 from ``next69_merge_heads``' tuple
  to resolve a ``KeyError`` from Alembic's head_maintainer (the
  ``depends_on`` link consumed 20250322 from the heads set, so it could no
  longer be merged explicitly). Side effect: 20250322 became an orphan
  head, breaking ``alembic upgrade head`` with "Multiple head revisions"
  (CI run 26316876414).
* iter-15g (this revision): the correct resolution is to use ONE
  mechanism, not two. Promote 20250322 from ``depends_on`` to an actual
  ``down_revision`` parent of this migration (tuple form). This makes
  20250322 a real interior node of the DAG — no longer a head, so
  next69 doesn't need to merge it. ``depends_on`` is now redundant and
  removed.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250501_reliability_outbox_webhook_delivery"
# iter-15g: tuple form makes this a merge revision with two parents.
# 20250322_add_webhook_subscriptions must apply before this migration so
# ``op.batch_alter_table("webhook_subscription")`` (line 32 of upgrade)
# finds the table. Previously this was enforced via ``depends_on``, but
# combining ``depends_on`` with explicit merge in ``next69_merge_heads``
# produced ``KeyError`` in head_maintainer. Single mechanism is cleaner.
down_revision: Union[str, Sequence[str], None] = (
    "20250430_client_portal_packages_mvp",
    "20250322_add_webhook_subscriptions",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        sa.UniqueConstraint(
            "subscription_id", "event_id", name="uq_webhook_delivery_subscription_event"
        ),
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
