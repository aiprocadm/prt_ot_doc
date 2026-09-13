"""Сторож НА ЗЕМЛЕ: миграции создают ровно то, что объявляют модели (срез-175).

ЗАЧЕМ. Обычный прогон тестов строит схему НЕ миграциями, а прямо из моделей
(`metadata.create_all` в conftest). Значит, колонка, которую модель объявила, а
миграция не создала, в тестах не видна вовсе: всё зелено, а на живой базе,
собранной миграциями, тот же запрос падает. Разбор по тексту
(`scripts/audit/check_orm_migration_drift.py`) про это кричал — 128 таблиц с
расхождением, из них 16 «критических», — но у него свои слепые пятна, и
проверить его можно только базой.

ЧТО ПОКАЗАЛА ЗЕМЛЯ (срез-175). Накат миграций на пустую базу: **ни одной
пропущенной таблицы и ни одной пропущенной колонки**. Все «критические»
находки разбора оказались ложными — он не связывает часть миграций с
таблицами. Зато нашлось обратное: 33 таблицы, которые миграции создают, а
модели их не знают.

КАК УСТРОЕН. Заводит временную базу, накатывает миграции, читает реальные
колонки и сверяет с объявленным. Занимает около 30 секунд и идёт только там,
где задан ``TEST_PG_ADMIN_URL`` — на SQLite такой проверки не бывает.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

#: Таблицы, которые миграции создают, а модели не объявляют.
#:
#: Это остаток прежних волн: контуры, переписанные на новые таблицы, а старые
#: снести не успели. Снос — решение владельца (в них могут быть данные), и он
#: записан отдельной темой. Здесь список нужен, чтобы новых таких таблиц НЕ
#: ПОЯВЛЯЛОСЬ: каждая — это миграция, создающая то, чем никто не пользуется.
TABLES_WITHOUT_MODEL = {
    "asset",
    "companies",
    "corrective_action_attachments",
    "departments",
    "documentgenerationjob",
    "edo_receipts",
    "equipment",
    "hazard_bindings",
    "hazard_measures",
    "incident_attachments",
    "incident_cases",
    "incident_investigations",
    "incident_persons",
    "inspection_attachments",
    "inspection_checklist_items",
    "inspection_checklists",
    "inspection_plan_items",
    "inspection_plans",
    "inspection_run_items",
    "inspection_runs",
    "npa",
    "ops_inspections",
    "persons",
    "positions",
    "prescription_items",
    "reminder_rules",
    "risk",
    "sites",
    "tenant_rate_limits",
    "training_plan_items",
    "training_plans",
    "training_protocol_items",
    "workplaces",
}

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="нужен TEST_PG_ADMIN_URL: сверка миграций с моделями идёт только на живой базе",
)


async def _admin(sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _columns(dsn: str) -> list[tuple[str, str]]:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT table_name, column_name FROM information_schema.columns"
            " WHERE table_schema = 'public'"
        )
        return [(row["table_name"], row["column_name"]) for row in rows]
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def schema_after_migrations() -> dict[str, set[str]]:
    """Реальные таблицы и колонки после наката миграций на пустую базу."""

    assert ADMIN_URL
    name = f"migcheck_{uuid.uuid4().hex[:10]}"
    target = f"{ADMIN_URL.rsplit('/', 1)[0]}/{name}"
    asyncio.run(_admin(f'CREATE DATABASE "{name}"'))
    try:
        async_dsn = target.replace("postgresql://", "postgresql+asyncpg://", 1)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                "backend/app/migrations/alembic.ini",
                "upgrade",
                "heads",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(REPO_ROOT / "backend"),
                "DATABASE_URL": async_dsn,
                "MIGRATION_DATABASE_URL": async_dsn,
            },
            timeout=1800,
        )
        assert result.returncode == 0, (
            "миграции не накатились на пустую базу:\n"
            f"{result.stdout[-3000:]}\n{result.stderr[-3000:]}"
        )

        schema: dict[str, set[str]] = {}
        for table, column in asyncio.run(_columns(target)):
            schema.setdefault(table, set()).add(column)
        return schema
    finally:
        asyncio.run(_admin(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def _declared() -> dict[str, set[str]]:
    import app.db.base  # noqa: F401 — подтягивает все модели
    from app.db.session import SharedBase, TenantBase

    declared: dict[str, set[str]] = {}
    for metadata in (SharedBase.metadata, TenantBase.metadata):
        for table in metadata.tables.values():
            declared[table.name] = {col.name for col in table.columns}
    return declared


def test_база_поднялась_и_не_пуста(schema_after_migrations: dict[str, set[str]]) -> None:
    assert len(schema_after_migrations) > 250, (
        f"после миграций таблиц всего {len(schema_after_migrations)} — " "проверка меряет не то"
    )


def test_миграции_создают_все_объявленные_таблицы(
    schema_after_migrations: dict[str, set[str]],
) -> None:
    missing = sorted(set(_declared()) - set(schema_after_migrations))
    assert not missing, (
        "модель объявляет таблицу, а миграции её не создают. В тестах это не "
        "видно (схема там строится из моделей), а на живой базе любой запрос к "
        "ней упадёт: " + ", ".join(missing)
    )


def test_миграции_создают_все_объявленные_колонки(
    schema_after_migrations: dict[str, set[str]],
) -> None:
    declared = _declared()
    problems: list[str] = []
    for name in sorted(set(declared) & set(schema_after_migrations)):
        gap = sorted(declared[name] - schema_after_migrations[name])
        if gap:
            problems.append(f"  {name}: {', '.join(gap)}")

    assert not problems, (
        "модель объявляет колонку, а миграции её не создают — на живой базе "
        "запрос к ней упадёт:\n" + "\n".join(problems)
    )


def test_новых_таблиц_без_модели_не_появилось(
    schema_after_migrations: dict[str, set[str]],
) -> None:
    orphans = set(schema_after_migrations) - set(_declared()) - {"alembic_version"}

    new_ones = sorted(orphans - TABLES_WITHOUT_MODEL)
    assert not new_ones, (
        "миграция создала таблицу, которой не соответствует ни одна модель — "
        "ею никто не пользуется: " + ", ".join(new_ones)
    )

    gone = sorted(TABLES_WITHOUT_MODEL - orphans)
    assert (
        not gone
    ), "таблица из списка «без модели» больше не сирота — уберите её из " "списка: " + ", ".join(
        gone
    )
