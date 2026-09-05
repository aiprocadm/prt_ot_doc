"""Сроки средств пожарной защиты в общем календаре и Центре внимания (срез-79).

ЗАЧЕМ. Разд. 54.1: «просрочки ТО/перезарядки, готовность к проверке МЧС».
Модуль ПБ считал их у себя в сводке ``/fire-safety/readiness``, а общий
календарь и Центр внимания (разд. 57.2 — «всё в одном месте») молчали:
строка «Пожарная безопасность» видела только противопожарные инструктажи.
Семь дисциплин из восьми имели источник сроков по таблице, ПБ — нет.

ЧТО ПРОВЕРЯЕТСЯ: контракт источника; календарь — просроченная перезарядка и
будущая поверка видны (вид в ``extra.kind``), списанное, удалённое и без
дат — нет; отбор по площадке; живьём — Центр внимания показывает срок
строкой «Пожарная безопасность», и его цифра совпадает со сводкой модуля.
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
from app.models.fire_safety import FireSafetyEquipment
from app.models.models import RoleEnum
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from app.services.discipline_deadline_events import DEADLINE_EVENT_SOURCES
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

TODAY = date.today()


def test_источник_объявлен_размечен_пб_по_площадке_и_в_обходе() -> None:
    assert "fire_safety_equipment" in ALL_SOURCES
    assert "fire_safety_equipment" in ATTENTION_SOURCES
    assert discipline_of("fire_safety_equipment") is Discipline.FIRE_SAFETY
    # огнетушитель висит на площадке, а не на человеке
    assert "fire_safety_equipment" not in PERSON_SCOPED_SOURCES
    assert "fire_safety_equipment" in DEADLINE_EVENT_SOURCES


def _unit(
    tenant_id: str, *, label: str, kind: str = "extinguisher", **extra
) -> FireSafetyEquipment:
    return FireSafetyEquipment(tenant_id=tenant_id, kind=kind, label=label, **extra)


class TestКалендарь:
    async def test_просроченная_перезарядка_и_будущая_поверка_видны_списанное_и_без_дат_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add_all(
            [
                # Перезарядка просрочена на 5 дней — горит.
                _unit(
                    tid,
                    label="ОП-4 №12",
                    location="Склад №1",
                    recharge_due=TODAY - timedelta(days=5),
                ),
                # Поверка системы через 20 дней — предупреждение.
                _unit(
                    tid,
                    label="АУПС корпус Б",
                    kind="alarm_system",
                    inspection_due=TODAY + timedelta(days=20),
                ),
                # Списанный огнетушитель с просроченной перезарядкой — шум.
                _unit(
                    tid,
                    label="ОП-4 №99",
                    status="decommissioned",
                    recharge_due=TODAY - timedelta(days=40),
                ),
                # Удалённый.
                _unit(
                    tid,
                    label="ОП-4 №100",
                    recharge_due=TODAY - timedelta(days=40),
                    deleted_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
                # Щит без сроков — не срок.
                _unit(tid, label="Щит №1", kind="shield"),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(
            source_types=["fire_safety_equipment"], include_sla=True
        )

        assert response.total == 2
        assert response.overdue_count == 1
        overdue, soon = response.items
        assert overdue.title == "Перезарядка: ОП-4 №12 (Склад №1)"
        assert overdue.status == "overdue"
        assert overdue.is_overdue is True
        assert overdue.sla_band == "overdue"
        assert overdue.extra["kind"] == "recharge"
        assert overdue.extra["equipment_kind"] == "extinguisher"
        assert overdue.id.endswith(":recharge")
        assert soon.title == "Поверка/ТО: АУПС корпус Б"
        assert soon.status == "valid"
        assert soon.is_overdue is False
        assert soon.sla_band == "warning"
        assert soon.extra["kind"] == "inspection"
        counts = {row.source_type: row for row in response.by_source}
        assert counts["fire_safety_equipment"].count == 2
        assert counts["fire_safety_equipment"].overdue_count == 1

    async def test_у_огнетушителя_два_срока_две_строки_и_отбор_по_площадке(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        site = await data_factory.create_site(tenant=tenant, session=test_db_session, name="Цех 1")
        test_db_session.add_all(
            [
                # Оба срока у одной единицы — две строки с разным видом.
                _unit(
                    tid,
                    label="ОП-5 №1",
                    site_id=site.id,
                    recharge_due=TODAY - timedelta(days=2),
                    inspection_due=TODAY - timedelta(days=1),
                ),
                # Другая площадка (без площадки).
                _unit(tid, label="ОП-5 №2", recharge_due=TODAY - timedelta(days=2)),
                # Чужой арендатор.
                _unit("someone-else", label="ОП-5 №3", recharge_due=TODAY - timedelta(days=2)),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        everything = await service.list_events(source_types=["fire_safety_equipment"])
        assert everything.total == 3
        assert everything.overdue_count == 3
        assert sorted(item.extra["kind"] for item in everything.items) == [
            "inspection",
            "recharge",
            "recharge",
        ]

        on_site = await service.list_events(
            source_types=["fire_safety_equipment"], site_id=str(site.id)
        )
        assert on_site.total == 2
        assert {item.site_id for item in on_site.items} == {str(site.id)}
        assert len({item.id for item in on_site.items}) == 2, "разные виды — разные id"


class TestЦентрВнимания:
    async def test_просроченная_перезарядка_доходит_до_центра_внимания_одной_цифрой_со_сводкой_пб(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Строка «Пожарная безопасность», пункт ленты и сводка модуля — одно число."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            await data_factory.set_modules(session, tenant.id, ("fire_safety",))
            tid = str(tenant.id)
            session.add_all(
                [
                    _unit(
                        tid,
                        label="ОП-4 №7",
                        location="Проходная",
                        recharge_due=TODAY - timedelta(days=3),
                    ),
                    _unit(
                        tid,
                        label="ПК-1",
                        kind="hydrant",
                        inspection_due=TODAY + timedelta(days=200),
                    ),
                    _unit(
                        tid,
                        label="ОП-4 №8",
                        status="decommissioned",
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
        items = [item for item in body["items"] if item["item_type"] == "fire_safety_equipment"]
        assert len(items) == 1, body["items"]
        assert items[0]["discipline"] == "fire_safety"
        assert items[0]["title"] == "Перезарядка: ОП-4 №7 (Проходная)"
        fire = next(row for row in body["disciplines"] if row["code"] == "fire_safety")
        assert fire["overdue"] == 1
        summary = readiness.json()
        assert (
            summary["overdue_recharge"] + summary["overdue_inspection"] == fire["overdue"]
        ), "сводка модуля и строка дисциплины — одно число"
