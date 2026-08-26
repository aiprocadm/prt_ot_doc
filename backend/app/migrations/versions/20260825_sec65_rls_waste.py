"""SEC-65 хвост: RLS для таблиц отходов (созданы в eco03).

Новые арендаторские таблицы обязаны быть вооружены на уровне БАЗЫ, а не только
tenant-фильтром в запросах: изоляция, которую держит лишь прикладной код,
теряется при первой же забытой ``where(tenant_id == ...)``. Исключением
(``RLS_EXEMPT_TABLES``) они быть не могут — это данные заказчика.

Паттерн — как в nvos_facility: ENABLE + FORCE + policy tenant_isolation
(PG-only, SQLite не умеет RLS).

Revision ID: 20260825_sec65_rls_waste
Revises: 20260825_eco03_waste
Create Date: 2026-08-25
"""

from __future__ import annotations

from alembic import op

revision = "20260825_sec65_rls_waste"
down_revision = "20260825_eco03_waste"
branch_labels = None
depends_on = None

_TABLES = ("waste_passport", "waste_movement")
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
