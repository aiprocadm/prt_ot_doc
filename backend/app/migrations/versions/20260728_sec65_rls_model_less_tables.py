"""SEC-65: RLS on the 8 tenant tables that have no ORM model.

Revision ID: 20260728_sec65_rls_model_less_tables
Revises: 20260727_sec65_rls_auth_queues_final
Create Date: 2026-07-28

Found by the new live-schema audit (``scripts/audit/check_rls_live_schema.py``),
which enumerates tenant tables from ``pg_attribute`` instead of SQLAlchemy
metadata. The ratchet guard builds its denominator from the ORM, so a table with
a ``tenant_id`` column but no model never entered the count of "265 tenant
tables" and could stay unarmed indefinitely — the same blind spot that hid
``webhook_subscriptions`` until the previous slice.

Eight such tables exist on a freshly migrated database:

  * ``20260401_next58_safety_core`` created PLURAL duplicates of the org registry —
    ``companies``, ``sites``, ``departments``, ``persons``, ``positions``,
    ``workplaces``. The ORM models are the SINGULAR ``company`` / ``site`` /
    ``department`` / ``person`` / ``position`` / ``workplace`` tables, which the
    ``20260724_sec65_rls_org_registry`` slice already armed.
  * ``20260317_next46_training_briefings_offline`` created ``training_plans`` and
    ``training_plan_items``; the ORM model is the singular ``training_plan``.

All eight carry ``tenant_id NOT NULL`` with a ``FOREIGN KEY … REFERENCES
tenant(id)``, so they hold real tenant data and no backfill is needed.

Why arm rather than drop. ``webhook_subscriptions`` was dropped because it was
provably empty and unreachable. These are not provably empty: this repository's
migrations create them on every deployment, and an operator's import or a
hand-written query may have filled them. Arming is non-destructive and closes the
exposure either way; deciding whether the duplicates should exist at all is a
data-model cleanup that belongs to its own change.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY``
makes it apply even to the table owner. PostgreSQL-only; on SQLite this is a
no-op.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_sec65_rls_model_less_tables"
down_revision: str | Sequence[str] | None = "20260727_sec65_rls_auth_queues_final"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted. No ORM model backs any of these — see the module docstring.
_TABLES = (
    "companies",
    "departments",
    "persons",
    "positions",
    "sites",
    "training_plan_items",
    "training_plans",
    "workplaces",
)

_POLICY = "tenant_isolation"

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # ENABLE/FORCE take ACCESS EXCLUSIVE; fail fast rather than queue traffic behind
    # a stuck transaction.
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in reversed(_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
