"""SEC-65 хвост: RLS для путевых листов (созданы в rs04).

Новая арендаторская таблица обязана быть вооружена на уровне БАЗЫ, а не только
tenant-фильтром в запросах: изоляция, которую держит лишь прикладной код,
теряется при первой же забытой ``where(tenant_id == ...)``. Данные к тому же
персональные — из листа видно, кто и когда выезжал и прошёл ли медосмотр,
поэтому ``RLS_EXEMPT_TABLES`` тут исключено.

Паттерн — как в road_vehicle и road_driver: ENABLE + FORCE + policy
tenant_isolation (PG-only, SQLite не умеет RLS).

Revision ID: 20260830_sec65_rls_waybills
Revises: 20260830_rs04_waybills
Create Date: 2026-08-30
"""

from __future__ import annotations

from alembic import op

revision = "20260830_sec65_rls_waybills"
down_revision = "20260830_rs04_waybills"
branch_labels = None
depends_on = None

_TABLES = ("road_waybill",)
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
