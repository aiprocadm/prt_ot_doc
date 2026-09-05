"""SEC-65 хвост: RLS для таблицы отчётов директору по дисциплинам (создана в dr01).

Таблицу завёл срез-53 (Доп. №1 разд. 57.4) без RLS-миграции; полный прогон
бэкенда поймал это сторожем ``tests/test_rls_coverage.py`` уже после
вливания. Новые арендаторские таблицы обязаны быть вооружены на уровне БАЗЫ,
а не только tenant-фильтром в запросах: изоляция, которую держит лишь
прикладной код, теряется при первой же забытой ``where(tenant_id == ...)``.
Исключением (``RLS_EXEMPT_TABLES``) отчёт быть не может — это сводка по
данным заказчика.

Паттерн — как в cd_drill: ENABLE + FORCE + policy tenant_isolation
(PG-only, SQLite не умеет RLS).

Revision ID: 20260905_sec65_rls_discipline_status_report
Revises: 20260904_dr02_discipline_report_notification
Create Date: 2026-09-05
"""

from __future__ import annotations

from alembic import op

revision = "20260905_sec65_rls_discipline_status_report"
down_revision = "20260904_dr02_discipline_report_notification"
branch_labels = None
depends_on = None

_TABLES = ("discipline_status_report",)
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
