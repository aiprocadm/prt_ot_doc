"""search.reindex.tick (BIZ-54-57 срез-128): ночная пересборка поискового снимка.

ЗАЧЕМ. Общий поиск и командная строка (CMD+K) читают ТОЛЬКО снимок
``search_index_entries`` — живого запроса к таблицам у них нет. А снимок
пересобирала одна ручка ``POST /search/reindex``: пока её никто не нажал,
поиск честно отвечал «ничего не найдено» по живым данным. Нанятый сегодня
человек не находился вовсе; удалённый находился до следующего нажатия.

Тот же случай, что проекции аналитики (срез-97) и снимок контрольных сроков
(срез-116): пересборка была написана и не была НИКЕМ позвана. Сторож против
повторения — ``tests/test_projection_rebuild_schedule.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.projections.models import SearchIndexEntry
from app.services.celery_app import celery_app

pytestmark = pytest.mark.anyio


def test_расписание_знает_ночную_пересборку_поиска() -> None:
    entry = celery_app.conf.beat_schedule["search-reindex-daily"]
    assert entry["task"] == "search.reindex.tick"
    assert "search.reindex.tick" in celery_app.tasks


async def test_нанятый_сегодня_находится_без_нажатия_кнопки(sessionmaker, data_factory) -> None:
    """Раньше новый человек не находился до тех пор, пока кто-то не нажмёт «переиндексировать»."""

    from app.tasks._core import _search_reindex_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="test", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Срез-128", session=session
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Нанят", session=session
        )
        await session.commit()
        tenant_id = str(tenant.id)
        person_id = str(person.id)

    total = await _search_reindex_tick()
    assert total >= 1

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(SearchIndexEntry).where(
                    SearchIndexEntry.tenant_id == tenant_id,
                    SearchIndexEntry.entity_type == "person",
                    SearchIndexEntry.entity_id == person_id,
                )
            )
        ).scalar_one()
    assert "Нанят" in (row.title or "")


async def test_уволенный_из_снимка_не_остаётся_навсегда(sessionmaker, data_factory) -> None:
    """Пересборка полная, а не досборка: иначе удалённая запись жила бы в поиске вечно."""

    from app.tasks._core import _search_reindex_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="test", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="ООО Срез-128", session=session
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Удалится", session=session
        )
        await session.commit()
        tenant_id = str(tenant.id)
        person_id = str(person.id)

    await _search_reindex_tick()

    from datetime import datetime, timezone

    from app.models.models import Person

    async with sessionmaker() as session:
        row = (await session.execute(select(Person).where(Person.id == person_id))).scalar_one()
        row.deleted_at = datetime.now(tz=timezone.utc)
        await session.commit()

    await _search_reindex_tick()

    async with sessionmaker() as session:
        found = (
            (
                await session.execute(
                    select(SearchIndexEntry).where(
                        SearchIndexEntry.tenant_id == tenant_id,
                        SearchIndexEntry.entity_type == "person",
                        SearchIndexEntry.entity_id == person_id,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert found == []
