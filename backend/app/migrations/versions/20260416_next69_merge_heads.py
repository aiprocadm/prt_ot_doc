"""NEXT-69: merge multiple Alembic heads into one.

Revision ID: 20260416_next69_merge_heads
Revises:
    20250322_risk_cards_action_plans,
    20260222_next21,
    20260306_tenant_core_registry,
    20260314_next40,
    20260317_next46,
    20260319_next_branding_profiles,
    20260321_next50_tenant_limits_billing_events,
    20260407_hotfix_templateversionstatus_active,
    20260411_next66,
    20260416_next68_template_scope_normalization
Create Date: 2026-04-16

History:
* iter-15f: removed ``20250322_add_webhook_subscriptions`` from the explicit
  down_revision tuple. iter-10 added ``depends_on = "20250322_add_webhook_
  subscriptions"`` to ``20250501_reliability_outbox_webhook_delivery`` (to
  fix a cross-branch UndefinedTableError on Postgres). The ``depends_on``
  link causes Alembic to consume 20250322 from the heads set before this
  merge revision runs, so naming it explicitly here as a merge parent
  raises ``KeyError: '20250322_add_webhook_subscriptions'`` in
  ``head_maintainer._delete_version`` (CI run 26316630899).
  20250322 is still applied — it is reachable from this merge revision
  transitively via 20250501 -> 20250601 -> 20260221_next7 -> ... -> next69
  (verified 21-node chain).
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20260416_next69_merge_heads"
down_revision: str | Sequence[str] | None = (
    # iter-15f: "20250322_add_webhook_subscriptions" intentionally omitted;
    # see module docstring. It still applies via 20250501.depends_on.
    "20250322_risk_cards_action_plans",
    "20260222_next21",
    "20260306_tenant_core_registry",
    "20260314_next40",
    "20260317_next46",
    "20260319_next_branding_profiles",
    "20260321_next50_tenant_limits_billing_events",
    "20260407_hotfix_templateversionstatus_active",
    "20260411_next66",
    "20260416_next68_template_scope_normalization",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Merge revision intentionally does not change schema.
    pass


def downgrade() -> None:
    # Merge revision intentionally does not change schema.
    pass
