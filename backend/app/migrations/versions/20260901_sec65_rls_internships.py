"""SEC-65 хвост: RLS для стажировок (созданы в tr06).

Новая арендаторская таблица обязана быть вооружена на уровне БАЗЫ, а не только
tenant-фильтром в запросах. Данные персональные: кто у кого стажировался и
сколько смен отработал.

Паттерн — как у остальных: ENABLE + FORCE + policy tenant_isolation (PG-only,
SQLite не умеет RLS).

Revision ID: 20260901_sec65_rls_internships
Revises: 20260901_tr06_internships
Create Date: 2026-09-01
"""

from __future__ import annotations

from alembic import op

revision = "20260901_sec65_rls_internships"
down_revision = "20260901_tr06_internships"
branch_labels = None
depends_on = None

_TABLES = ("internship",)
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
