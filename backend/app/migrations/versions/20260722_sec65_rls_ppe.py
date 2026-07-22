"""SEC-65: RLS second-line tenant isolation — extend to the PPE (СИЗ) domain.

Revision ID: 20260722_sec65_rls_ppe
Revises: 20260722_sec65_rls_medical
Create Date: 2026-07-22

Applies the RLS shape proven in the committees pilot to the 9 PPE tables (norms,
items, issuances, suppliers, safety budget, stock batches/movements, inventory
counts). Three legacy tables predate the ``ppe_`` naming convention and are spelled
without an underscore (``ppenorm``/``ppeitem``/``ppeissue``); the names below come
from live SQLAlchemy metadata, not the class names.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner.

PostgreSQL-only: upgrade/downgrade short-circuit on any non-postgres dialect.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_sec65_rls_ppe"
down_revision: str | Sequence[str] | None = "20260722_sec65_rls_medical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "ppenorm",
    "ppeitem",
    "ppeissue",
    "ppe_supplier",
    "ppe_safety_budget",
    "ppe_stock_batch",
    "ppe_stock_movement",
    "ppe_inventory_count",
    "ppe_inventory_count_line",
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
    for table in reversed(_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
