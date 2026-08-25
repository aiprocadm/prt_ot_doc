"""SEC-65 хвост: RLS для nvos_facility (создана в eco01).

Новая арендаторская таблица обязана быть вооружена на уровне БАЗЫ, а не только
tenant-фильтром в запросах: изоляция, которую держит лишь прикладной код,
теряется при первой же забытой ``where(tenant_id == ...)``. Исключением
(``RLS_EXEMPT_TABLES``) она быть не может — это данные заказчика.

Паттерн — как в hazardous_facility: ENABLE + FORCE + policy tenant_isolation
(PG-only, SQLite не умеет RLS).

Revision ID: 20260825_sec65_rls_nvos
Revises: 20260825_eco01_nvos_facility
Create Date: 2026-08-25
"""

from __future__ import annotations

from alembic import op

revision = "20260825_sec65_rls_nvos"
down_revision = "20260825_eco01_nvos_facility"
branch_labels = None
depends_on = None

_TABLE = "nvos_facility"
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
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{_POLICY}" ON "{_TABLE}" '
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')
