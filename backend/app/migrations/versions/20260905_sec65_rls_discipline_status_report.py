"""SEC-65 хвост: RLS для таблицы отчётов директору по дисциплинам (создана в dr01).

Таблицу завёл срез-53 (Доп. №1 разд. 57.4); сторож ``tests/test_rls_coverage.py``
потребовал RLS-миграцию, и эта миграция появилась. Но dr01 УЖЕ вооружил
таблицу (ENABLE + FORCE + policy ``tenant_isolation``, см.
``20260904_dr01_discipline_status_report.py``) — сторож ругался на реестр
``RLS_ENABLED_TABLES``, а не на базу. Повторный ``CREATE POLICY`` с тем же
именем падает: ``DuplicateObjectError: policy "tenant_isolation" ... already
exists`` — и с 05.09.2026 ``alembic upgrade heads`` на свежем PostgreSQL не
доходил до конца (PG-сторож ``backend/tests/test_alembic_postgres_upgrade.py``
пропускается без ``TEST_PG_ADMIN_URL``, поэтому полный прогон этого не видел;
нашлось 10.09.2026 при съёмке миграции среза-142).

Теперь миграция вооружает таблицу только если политики ещё нет — то есть
для баз, где dr01 отработал, она пустая, а для баз без dr01 (таких быть не
должно — dr01 идёт раньше в цепочке) по-прежнему защищает. Откат — пустой:
политику завёл dr01, он её и снимает.

Паттерн — как в cd_drill: ENABLE + FORCE + policy tenant_isolation
(PG-only, SQLite не умеет RLS).

Revision ID: 20260905_sec65_rls_discipline_status_report
Revises: 20260904_dr02_discipline_report_notification
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
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


def _policy_exists(bind, table: str) -> bool:
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_policies WHERE tablename = :table AND policyname = :policy"),
        {"table": table, "policy": _POLICY},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in _TABLES:
        if _policy_exists(bind, table):
            continue  # dr01 уже вооружил таблицу — повторный CREATE POLICY упал бы
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    # Политику завёл dr01 — он её и снимает при своём откате.
    return None
