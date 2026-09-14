"""SEC-65: RLS для таблиц срезов 189 и 192 (домены партнёра, профили импорта).

Revision ID: 20260914_sec65_rls_domains_and_profiles
Revises: 20260914_biz51_report_autosend
Create Date: 2026-09-14

Сторож ``tests/test_rls_coverage.py`` потребовал вооружить обе новые таблицы, и
потребовал по делу — это не формальность реестра:

* ``import_profiles`` хранит ЗАГОЛОВКИ чужой выгрузки. В них встречаются
  названия подразделений и фамилии — я сам написал это в описании модели и тут
  же завёл таблицу без второго рубежа изоляции;
* ``tenant_domains`` хранит домены партнёров и слова подтверждения. Увидеть
  чужое слово подтверждения — значит получить возможность заявить чужой домен
  раньше владельца.

RLS здесь — ВТОРОЙ рубеж: запросы и так идут со скоупом арендатора, но
единственная забытая фильтрация в будущем коде превращается в утечку. Ровно
для этого разд. 65 и существует.

Паттерн общий для всех RLS-миграций: ENABLE + FORCE + политика
``tenant_isolation`` (PG-only, SQLite не умеет RLS). Проверка «политика уже
есть» — урок 05.09: повторный CREATE POLICY с тем же именем валит весь накат.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260914_sec65_rls_domains_and_profiles"
down_revision = "20260914_biz51_report_autosend"
branch_labels = None
depends_on = None

_TABLES = ("tenant_domains", "import_profiles")
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
            continue
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
