"""OPS-72 срез-3 — порядок удаления на ЖИВОЙ схеме PostgreSQL (db-marked).

Циклы внешних ключей — свойство настоящей схемы, а не моделей: часть
tenant-таблиц создана миграциями и модели не имеет. И SQLite по умолчанию
внешние ключи вообще не проверяет, поэтому «на SQLite прошло» не говорит ничего
о безопасности порядка удаления.

Здесь проверяется главное свойство: на схеме, поднятой миграциями с нуля,
порядок удаления СТРОИТСЯ, а разорваны при этом только НЕОБЯЗАТЕЛЬНЫЕ ссылки —
то есть удаление не потеряет данных в обязательных связях.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

# Те три цикла, из-за которых срез-2 остановился на плане.
EXPECTED_CYCLE_CHILDREN = {"template", "document", "medical_exam"}


def _sync_base() -> str:
    assert ADMIN_URL
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
    from pathlib import Path

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


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the purge order guard")
def test_real_schema_orders_and_breaks_only_nullable_links() -> None:
    async def _run() -> None:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.core.rls_policy import RLS_ENABLED_TABLES
        from app.modules.offboarding.schema_graph import reflect_schema_graph

        engine = create_async_engine(_async_url(dbname))
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                graph = await reflect_schema_graph(session, RLS_ENABLED_TABLES)
        finally:
            await engine.dispose()

        assert graph.tables, "схема поднята — tenant-таблицы обязаны найтись"
        order, broken = graph.deletion_order(graph.tables)

        assert len(order) == len(graph.tables), "каждая таблица обязана попасть в порядок"
        assert all(link.nullable for link in broken), (
            "разрывать можно только необязательные ссылки: "
            f"{[link.describe() for link in broken if not link.nullable]}"
        )
        assert EXPECTED_CYCLE_CHILDREN <= {link.child for link in broken}, (
            "известные циклы схемы должны разрываться явно: "
            f"{[link.describe() for link in broken]}"
        )

        # Порядок обязан быть согласован со ВСЕМИ неразорванными ссылками:
        # ребёнок удаляется раньше родителя, иначе внешний ключ остановит
        # удаление на середине.
        broken_keys = {(link.child, link.parent, link.columns) for link in broken}
        position = {table: index for index, table in enumerate(order)}
        for link in graph.links:
            if link.child == link.parent or (link.child, link.parent, link.columns) in broken_keys:
                continue
            if link.child in position and link.parent in position:
                assert position[link.child] < position[link.parent], link.describe()

    dbname = f"purge_order_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the purge execution guard")
def test_purge_executes_on_a_real_schema_with_enforced_foreign_keys() -> None:
    """Настоящая проверка среза: удаление проходит там, где внешние ключи
    ДЕЙСТВИТЕЛЬНО проверяются, и данные создавались через цикличные таблицы
    (``document`` ↔ ``documentgenerationjob``, ``template`` ↔ ``templateversion``)."""

    async def _run() -> None:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.modules.offboarding.purge import TenantPurgeService
        from tests.utils.factories import TestDataFactory

        class _NullStorage:
            def delete(self, key: str) -> None:  # noqa: D401 - заглушка хранилища
                return None

        engine = create_async_engine(_async_url(dbname))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            factory = TestDataFactory(maker)
            async with maker() as session:
                tenant = await factory.ensure_tenant(slug="purge-pg", session=session)
                neighbour = await factory.ensure_tenant(slug="purge-pg-next", session=session)
                # Документ тянет за собой template + templateversion + person +
                # company + user — ровно участников циклов.
                for index, owner in enumerate((tenant, neighbour)):
                    template = await factory.create_template(
                        tenant=owner, session=session, code=f"purge-pg-{index}"
                    )
                    await factory.create_document(
                        tenant=owner, template=template, session=session
                    )
                await session.commit()

                service = TenantPurgeService(
                    session,
                    tenant_id=str(tenant.id),
                    tenant_slug=tenant.slug,
                    storage=_NullStorage(),
                )
                # Заявитель — реальный пользователь, которого удаление сотрёт:
                # акт обязан пережить своего автора (FK ON DELETE SET NULL).
                requester = await factory.create_user(
                    tenant=tenant, session=session, email="owner-purge-pg@example.com"
                )
                await service.lifecycle.request(
                    grace_days=0,
                    actor_user_id=str(requester.id),
                    actor_email=requester.email,
                )
                await session.commit()

                act = await service.execute()
                await session.commit()

                assert act.rows_deleted > 0
                assert {"document", "template", "person"} <= set(act.deleted_rows)
                for table in ("document", "documentversion", "template", "person", "company"):
                    remaining = (
                        await session.execute(
                            text(f'SELECT count(*) FROM "{table}" WHERE tenant_id = :t'),
                            {"t": str(tenant.id)},
                        )
                    ).scalar_one()
                    assert remaining == 0, f"{table}: осталось {remaining} строк"
                # Соседний арендатор не задет — на необратимой операции это
                # единственная ошибка, которая ничем не лечится.
                neighbour_docs = (
                    await session.execute(
                        text("SELECT count(*) FROM document WHERE tenant_id = :t"),
                        {"t": str(neighbour.id)},
                    )
                ).scalar_one()
                assert neighbour_docs == 1

                # Акт пережил удаление вместе со своим автором.
                surviving = (
                    await session.execute(
                        text(
                            "SELECT status, requested_by_user_id, requested_by_email "
                            "FROM tenant_offboarding WHERE tenant_id = :t"
                        ),
                        {"t": str(tenant.id)},
                    )
                ).one()
                assert surviving[0] == "purged"
                assert surviving[1] is None, "ссылка на удалённого пользователя обнулена"
                assert surviving[2] == requester.email
        finally:
            await engine.dispose()

    dbname = f"purge_exec_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)
