"""SEC-65 хвост: RLS для fire_document (создана в fs05).

Новая арендаторская таблица обязана быть вооружена на уровне БАЗЫ, а не только
tenant-фильтром в запросах: изоляция, которую держит лишь прикладной код,
теряется при первой же забытой ``where(tenant_id == ...)``. Исключением
(``RLS_EXEMPT_TABLES``) она быть не может — это данные заказчика.

Паттерн — как в fire_maintenance: ENABLE + FORCE + policy tenant_isolation
(PG-only, SQLite не умеет RLS).

Revision ID: 20260824_sec65_rls_fire_doc
Revises: 20260824_fs05_fire_document
Create Date: 2026-08-24
"""

from __future__ import annotations

from alembic import op

revision = "20260824_sec65_rls_fire_doc"
down_revision = "20260824_fs05_fire_document"
branch_labels = None
depends_on = None

_TABLE = "fire_document"
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
