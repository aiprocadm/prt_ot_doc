"""Тренировки и документы ПБ в общем календаре и Центре внимания (срез-80).

ЗАЧЕМ. Разд. 54.1 требует вести план-график тренировок и учёт документов ПБ
со сроком пересмотра, разд. 57.2 — «всё в одном месте». Срез-79 подключил
к календарю сроки средств защиты, а сводка модуля ПБ считала ещё два числа,
которых календарь не знал: ``overdue_drills`` (тренировка не проведена к
плановой дате) и ``overdue_documents`` (пересмотр документа просрочен).
Ответственный за ПБ на странице модуля видел «тренировок просрочено: 1,
документов: 1», а строка «Пожарная безопасность» в Центре внимания — только
средства защиты.

ЧТО ПРОВЕРЯЕТСЯ: контракт двух источников; календарь — не проведённая к
дате тренировка и просроченный пересмотр видны, проведённая тренировка,
бессрочный и удалённый документ — нет; отбор по площадке; живьём — строка
«Пожарная безопасность» и сводка модуля дают одно число уже по трём
слагаемым.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import (
    ATTENTION_SOURCES,
    PERSON_SCOPED_SOURCES,
    Discipline,
    discipline_of,
)
from app.models.fire_safety import FireDrill, FireSafetyDocument, FireSafetyEquipment
from app.models.models import RoleEnum
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from app.services.discipline_deadline_events import DEADLINE_EVENT_SOURCES
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

TODAY = date.today()
SOURCES = ("fire_safety_drill", "fire_safety_document")


@pytest.mark.parametrize("source", SOURCES)
def test_источник_объявлен_размечен_пб_по_площадке_и_в_обходе(source: str) -> None:
    assert source in ALL_SOURCES
    assert source in ATTENTION_SOURCES
    assert discipline_of(source) is Discipline.FIRE_SAFETY
    # тренировка и документ — про объект, не про человека
    assert source not in PERSON_SCOPED_SOURCES
    assert source in DEADLINE_EVENT_SOURCES


def _drill(tenant_id: str, *, title: str, planned_on: date, **extra) -> FireDrill:
    return FireDrill(
        tenant_id=tenant_id,
        kind=extra.pop("kind", "evacuation"),
        title=title,
        planned_on=planned_on,
        **extra,
    )


def _document(tenant_id: str, *, title: str, **extra) -> FireSafetyDocument:
    return FireSafetyDocument(
        tenant_id=tenant_id, kind=extra.pop("kind", "instruction_general"), title=title, **extra
    )


class TestКалендарь:
    async def test_не_проведённая_тренировка_видна_проведённая_и_удалённая_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add_all(
            [
                # Плановая дата прошла 5 дней назад, протокола нет — не проведена.
                _drill(tid, title="Эвакуация корпус А", planned_on=TODAY - timedelta(days=5)),
                # Запланирована через 20 дней — предупреждение.
                _drill(
                    tid,
                    title="Тушение на складе",
                    kind="fire_fighting",
                    planned_on=TODAY + timedelta(days=20),
                ),
                # Проведена (есть протокол) — не срок.
                _drill(
                    tid,
                    title="Эвакуация корпус Б",
                    planned_on=TODAY - timedelta(days=10),
                    held_on=TODAY - timedelta(days=9),
                    outcome="passed",
                ),
                # Удалённая.
                _drill(
                    tid,
                    title="Удалённая",
                    planned_on=TODAY - timedelta(days=5),
                    deleted_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(source_types=["fire_safety_drill"], include_sla=True)

        assert response.total == 2
        assert response.overdue_count == 1
        overdue, soon = response.items
        assert overdue.title == "Тренировка ПБ: Эвакуация корпус А"
        assert overdue.status == "overdue"
        assert overdue.is_overdue is True
        assert overdue.sla_band == "overdue"
        assert overdue.extra["kind"] == "evacuation"
        assert soon.title == "Тренировка ПБ: Тушение на складе"
        assert soon.status == "planned"
        assert soon.is_overdue is False
        assert soon.sla_band == "warning"
        assert soon.extra["kind"] == "fire_fighting"
        counts = {row.source_type: row for row in response.by_source}
        assert counts["fire_safety_drill"].count == 2
        assert counts["fire_safety_drill"].overdue_count == 1

    async def test_просроченный_пересмотр_виден_бессрочный_и_удалённый_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add_all(
            [
                # Пересмотр просрочен на 5 дней.
                _document(
                    tid,
                    title="Инструкция склада №1",
                    kind="instruction_room",
                    location="Склад №1",
                    review_due=TODAY - timedelta(days=5),
                ),
                # Пересмотр через 20 дней — предупреждение; номер входит в заголовок.
                _document(
                    tid,
                    title="О назначении ответственных за ПБ",
                    kind="order",
                    number="12-ПБ",
                    review_due=TODAY + timedelta(days=20),
                ),
                # Бессрочный — не срок.
                _document(tid, title="Журнал учёта огнетушителей", kind="journal"),
                # Удалённый.
                _document(
                    tid,
                    title="Удалённый",
                    review_due=TODAY - timedelta(days=5),
                    deleted_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(
            source_types=["fire_safety_document"], include_sla=True
        )

        assert response.total == 2
        assert response.overdue_count == 1
        overdue, soon = response.items
        assert (
            overdue.title
            == "Пересмотр: Инструкция о мерах ПБ (по помещению) — Инструкция склада №1"
        )
        assert overdue.status == "overdue"
        assert overdue.is_overdue is True
        assert overdue.sla_band == "overdue"
        assert overdue.extra["kind"] == "instruction_room"
        assert overdue.extra["location"] == "Склад №1"
        assert soon.title == "Пересмотр: Приказ № 12-ПБ — О назначении ответственных за ПБ"
        assert soon.status == "valid"
        assert soon.is_overdue is False
        assert soon.sla_band == "warning"
        counts = {row.source_type: row for row in response.by_source}
        assert counts["fire_safety_document"].count == 2
        assert counts["fire_safety_document"].overdue_count == 1

    async def test_отбор_по_площадке_и_чужой_арендатор_невидим(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        site = await data_factory.create_site(tenant=tenant, session=test_db_session, name="Цех 1")
        test_db_session.add_all(
            [
                _drill(
                    tid, title="На площадке", planned_on=TODAY - timedelta(days=2), site_id=site.id
                ),
                _drill(tid, title="Без площадки", planned_on=TODAY - timedelta(days=2)),
                _document(
                    tid,
                    title="План эвакуации цеха",
                    kind="evacuation_plan",
                    review_due=TODAY - timedelta(days=1),
                    site_id=site.id,
                ),
                _document(
                    tid, title="Общий приказ", kind="order", review_due=TODAY - timedelta(days=1)
                ),
                _drill("someone-else", title="Чужая", planned_on=TODAY - timedelta(days=2)),
                _document("someone-else", title="Чужой", review_due=TODAY - timedelta(days=1)),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        everything = await service.list_events(source_types=list(SOURCES))
        assert everything.total == 4
        assert everything.overdue_count == 4

        on_site = await service.list_events(source_types=list(SOURCES), site_id=str(site.id))
        assert on_site.total == 2
        assert {item.site_id for item in on_site.items} == {str(site.id)}
        assert {item.source_type for item in on_site.items} == set(SOURCES)


class TestЦентрВнимания:
    async def test_тренировка_и_документ_доходят_до_центра_внимания_одной_цифрой_со_сводкой_пб(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Строка «Пожарная безопасность» = средства + тренировки + документы сводки."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await data_factory.set_modules(session, tenant.id, ("fire_safety",))
            tid = str(tenant.id)
            session.add_all(
                [
                    _drill(tid, title="Эвакуация корпус А", planned_on=TODAY - timedelta(days=3)),
                    _drill(
                        tid,
                        title="Проведённая",
                        planned_on=TODAY - timedelta(days=30),
                        held_on=TODAY - timedelta(days=30),
                        outcome="passed",
                    ),
                    _document(
                        tid, title="Инструкция общеобъектовая", review_due=TODAY - timedelta(days=2)
                    ),
                    _document(tid, title="Журнал", kind="journal"),
                    FireSafetyEquipment(
                        tenant_id=tid,
                        kind="extinguisher",
                        label="ОП-4 №7",
                        recharge_due=TODAY - timedelta(days=3),
                    ),
                ]
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        attention = await async_client.get("/api/v1/workspace/attention", headers=headers)
        readiness = await async_client.get("/api/v1/fire-safety/readiness", headers=headers)

        assert attention.status_code == 200, attention.text
        assert readiness.status_code == 200, readiness.text
        body = attention.json()
        by_type = {}
        for item in body["items"]:
            by_type.setdefault(item["item_type"], []).append(item)
        assert [i["title"] for i in by_type.get("fire_safety_drill", [])] == [
            "Тренировка ПБ: Эвакуация корпус А"
        ]
        assert [i["title"] for i in by_type.get("fire_safety_document", [])] == [
            "Пересмотр: Инструкция о мерах ПБ (общеобъектовая) — Инструкция общеобъектовая"
        ]
        assert all(i["discipline"] == "fire_safety" for t in SOURCES for i in by_type.get(t, []))
        fire = next(row for row in body["disciplines"] if row["code"] == "fire_safety")
        assert fire["overdue"] == 3
        summary = readiness.json()
        assert summary["overdue_drills"] == 1
        assert summary["overdue_documents"] == 1
        assert (
            summary["overdue_recharge"]
            + summary["overdue_inspection"]
            + summary["overdue_drills"]
            + summary["overdue_documents"]
            == fire["overdue"]
        ), "сводка модуля и строка дисциплины — одно число"
