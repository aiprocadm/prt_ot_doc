"""ПБ срез-3 (Доп. №1 разд. 54.1): противопожарные инструктажи и ПТМ.

ТЗ: «Противопожарные инструктажи и ПТМ: вводный/первичный/повторный/
внеплановый/целевой, пожарно-технический минимум, журналы, контроль сроков».

**Что нашла сверка.** Инструктажи в системе есть, но ``briefing_type`` был
СВОБОДНОЙ СТРОКОЙ: записать можно было что угодно, а отличить противопожарный
инструктаж от инструктажа по охране труда — нечем. Значит «контроль сроков»
по пожарной дисциплине был невыполним по построению, а комментарий в ядре
(``SOURCE_DISCIPLINE``) прямо это фиксировал: «пожарного вида среди них нет».

Сделано: закрытый словарь видов с дисциплиной, валидация на записи и счётчик
просроченных противопожарных инструктажей в готовности к проверке МЧС.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.disciplines import (
    BRIEFING_TYPE_DISCIPLINE,
    BRIEFING_TYPE_TITLES,
    BRIEFING_TYPES,
    Discipline,
    discipline_of_briefing,
)
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio


class TestСловарьВидов:
    def test_пожарные_виды_названы_поимённо(self) -> None:
        """ТЗ перечисляет их прямо — словарь обязан содержать все шесть."""

        fire = {
            code
            for code, discipline in BRIEFING_TYPE_DISCIPLINE.items()
            if discipline is Discipline.FIRE_SAFETY
        }
        assert fire == {
            "fire_introductory",
            "fire_primary",
            "fire_repeat",
            "fire_unscheduled",
            "fire_targeted",
            "fire_ptm",
        }

    def test_у_каждого_вида_есть_подпись_словами(self) -> None:
        """Код уходит в журнал и на экран — человек читает подпись, не код."""

        assert set(BRIEFING_TYPE_TITLES) == set(BRIEFING_TYPES)
        assert all(title.strip() for title in BRIEFING_TYPE_TITLES.values())

    def test_незнакомый_вид_не_получает_выдуманной_дисциплины(self) -> None:
        assert discipline_of_briefing("periodic") is None
        assert discipline_of_briefing("fire_ptm") is Discipline.FIRE_SAFETY


async def _grant_fire(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == "fire_safety"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="fire_safety", title="fire_safety")
            session.add(feature)
            await session.flush()
        grant = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            session.add(
                FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=True)
            )
        else:
            grant.on = True
        await session.commit()


class TestКонтрольСроков:
    async def test_неизвестный_вид_отвергается_словами(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.post(
            "/api/v1/briefings/templates",
            json={
                "code": "T-1",
                "title": "Шаблон",
                "briefing_type": "teleport",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text
        assert "Неизвестный вид инструктажа" in response.text

    async def test_просроченный_пожарный_инструктаж_виден_в_готовности(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Просроченный ПТМ — такое же нарушение к приходу МЧС, как
        непроверенный огнетушитель, и обязан попадать в ту же сводку."""

        headers = await make_auth_headers()
        await _grant_fire(sessionmaker)

        before = (
            await async_client.get("/api/v1/fire-safety/readiness", headers=headers)
        ).json()

        async with sessionmaker() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "test"))
            ).scalar_one()
            journal = BriefingJournal(
                tenant_id=tenant.id,
                code="J-FIRE",
                title="Журнал ПБ",
                journal_type="fire",
            )
            session.add(journal)
            await session.flush()
            session.add(
                BriefingEntry(
                    tenant_id=tenant.id,
                    briefing_journal_id=journal.id,
                    briefing_type="fire_ptm",
                    briefing_date=datetime.now(timezone.utc) - timedelta(days=400),
                    valid_until=datetime.now(timezone.utc) - timedelta(days=35),
                    status="done",
                )
            )
            # инструктаж по ОХРАНЕ ТРУДА, тоже просроченный, — в пожарную
            # сводку попадать НЕ должен
            session.add(
                BriefingEntry(
                    tenant_id=tenant.id,
                    briefing_journal_id=journal.id,
                    briefing_type="repeat",
                    briefing_date=datetime.now(timezone.utc) - timedelta(days=400),
                    valid_until=datetime.now(timezone.utc) - timedelta(days=35),
                    status="done",
                )
            )
            await session.commit()

        after = (
            await async_client.get("/api/v1/fire-safety/readiness", headers=headers)
        ).json()
        assert (
            after["overdue_fire_briefings"] == before["overdue_fire_briefings"] + 1
        ), after
