"""SEC-65 хвост: RLS для нарушений ПДД (созданы в rs06).

Новая арендаторская таблица обязана быть вооружена на уровне БАЗЫ. Данные
персональные и чувствительные: кто нарушил, на чём, сколько заплатила
организация.

Паттерн — как у остальных таблиц контура: ENABLE + FORCE + policy
tenant_isolation (PG-only, SQLite не умеет RLS).

Revision ID: 20260901_sec65_rls_violations
Revises: 20260901_rs06_violations
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op

revision = "20260901_sec65_rls_violations"
down_revision = "20260901_rs06_violations"
branch_labels = None
depends_on = None

_TABLES = ("road_violation",)
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
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
    for table in _TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
