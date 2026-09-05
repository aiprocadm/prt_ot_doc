"""SEC-65 хвост: RLS для ``discipline_status_report`` (отчёт директору, разд. 57.4).

Таблицу завёл срез-53 без RLS-миграции; сторож ``tests/test_rls_coverage.py``
поймал это в полном прогоне уже после вливания. Здесь два уровня:

* без базы — миграция существует, целит в нужную таблицу, стоит в цепочке
  за ``dr02`` и повторяет общий предикат (иначе реестр говорил бы правду о
  файле, которого нет);
* на PostgreSQL (``TEST_PG_ADMIN_URL``) — миграция реально вооружила таблицу:
  ENABLE + FORCE + policy ``tenant_isolation``. Семантика политики доказана
  в ``test_rls_committees.py``, предикат тот же.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

from app.core.rls_policy import RLS_ENABLED_TABLES, RLS_EXEMPT_TABLES

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
TABLE = "discipline_status_report"
REVISION = "20260905_sec65_rls_discipline_status_report"
MIGRATIONS = Path(__file__).resolve().parents[1] / "app" / "migrations" / "versions"


def _load_migration(revision: str):
    path = MIGRATIONS / f"{revision}.py"
    spec = importlib.util.spec_from_file_location(revision, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_таблица_в_реестре_и_миграция_целит_в_неё() -> None:
    assert TABLE in RLS_ENABLED_TABLES
    assert TABLE not in RLS_EXEMPT_TABLES, "сводка по данным заказчика исключением быть не может"
    migration = _load_migration(REVISION)
    assert migration.revision == REVISION
    assert migration.down_revision == "20260904_dr02_discipline_report_notification"
    assert migration._TABLES == (TABLE,)
    assert migration._POLICY == "tenant_isolation"
    # тот же предикат, что у остальных SEC-65 миграций — иначе обход/контекст
    # арендатора у этой таблицы работал бы иначе, чем у соседей
    reference = _load_migration("20260827_sec65_rls_cd_drill")
    assert migration._PREDICATE == reference._PREDICATE


def _sync_base() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str) -> str:
    base = _sync_base().replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


async def _admin_exec(sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _upgrade(dbname: str) -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = _async_url(dbname)
    get_settings.cache_clear()
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "app" / "migrations"))
    command.upgrade(cfg, "heads")


def _teardown(dbname: str) -> None:
    asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.db
@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS guard")
def test_migration_arms_discipline_status_report() -> None:
    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            cls = await conn.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = $1",
                TABLE,
            )
            assert cls is not None, f"table {TABLE} missing"
            assert cls["relrowsecurity"], f"RLS not enabled on {TABLE}"
            assert cls["relforcerowsecurity"], f"FORCE RLS not set on {TABLE}"
            using = await conn.fetchval(
                """
                SELECT pg_get_expr(p.polqual, p.polrelid)
                FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
                WHERE c.relname = $1 AND p.polname = 'tenant_isolation'
                """,
                TABLE,
            )
            assert using is not None, f"tenant_isolation policy missing on {TABLE}"
            assert "app.current_tenant" in using and "app.bypass_rls" in using
            assert "tenant_id" in using
        finally:
            await conn.close()

    dbname = f"rls_dsr_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)
