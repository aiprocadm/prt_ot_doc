"""Просроченные сроки дисциплин → события для правил (BIZ-54-57 срез-62).

Доп. №1 разд. 57.3, приёмка §58.3: библиотека правил — «для каждой
дисциплины». Экология, ГО и ЧС и БДД не испускали событий, и правил по ним
не было. Здесь проверяется обход общего календаря, который превращает их
просрочки в событие ``DisciplineDeadlineOverdue``:

- событие получает ТОЛЬКО просроченная строка, и ровно один раз на срок:
  повторный обход в тот же день — ноль; продлили и снова просрочили — новое;
- четыре срока машины различаются видом в ключе — иначе истёкшие техосмотр
  и ОСАГО схлопнулись бы в одно событие;
- дисциплина без модуля молчит: у арендатора без «ГО и ЧС» просроченное
  учение событием не становится, и это названо в итоге;
- окно — как у Центра внимания: полугодовой давности просрочка — архив;
- потолок обхода назван, а не проглочен;
- (срез-72) срок отчётности или платежа эколога (срез-71) — событие с видом
  в ключе; исполненный срок событием не становится.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline
from app.models.civil_defense import CivilDefenseDrill
from app.models.ecology import EcologyReportingDeadline
from app.models.master_data import Person
from app.models.models import Company, Outbox
from app.models.road_safety import Driver, Vehicle
from app.services import discipline_deadline_events as svc
from app.services.discipline_deadline_events import (
    DEADLINE_EVENT_SOURCES,
    emit_overdue_deadline_events,
)
from app.services.events import EventType

pytestmark = pytest.mark.asyncio

TODAY = date.today()
EVENT = EventType.DISCIPLINE_DEADLINE_OVERDUE.value


async def _driver(
    session: AsyncSession, tenant_id: str, *, last_name: str, license_due, status="admitted"
):
    company = (
        (await session.execute(select(Company).where(Company.tenant_id == tenant_id)))
        .scalars()
        .first()
    )
    if company is None:
        company = Company(tenant_id=tenant_id, name="ООО Автобаза")
        session.add(company)
        await session.flush()
    person = Person(
        tenant_id=tenant_id, company_id=company.id, first_name="Пётр", last_name=last_name
    )
    session.add(person)
    await session.flush()
    driver = Driver(
        tenant_id=tenant_id,
        person_id=person.id,
        license_number=f"77 {last_name}",
        categories=["B"],
        license_due=license_due,
        status=status,
    )
    session.add(driver)
    await session.flush()
    return driver


async def _tenant(sessionmaker, data_factory, modules=("road_safety", "civil_defense")) -> str:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        if modules:
            await data_factory.set_modules(session, tenant.id, tuple(modules))
        await session.commit()
        return str(tenant.id)


async def _events(sessionmaker, tenant_id: str) -> list[Outbox]:
    async with sessionmaker() as session:
        return list(
            (
                await session.execute(
                    select(Outbox).where(Outbox.tenant_id == tenant_id, Outbox.event_type == EVENT)
                )
            )
            .scalars()
            .all()
        )


async def _run(sessionmaker, tenant_id: str):
    async with sessionmaker() as session:
        outcome = await emit_overdue_deadline_events(session, tenant_id=tenant_id)
        await session.commit()
        return outcome


def test_обходятся_только_источники_пяти_дисциплин() -> None:
    """Ядро (медосмотры, СИЗ) сюда не входит — у него свои события просрочки."""

    from app.core.disciplines import SOURCE_DISCIPLINE

    for source in DEADLINE_EVENT_SOURCES:
        assert SOURCE_DISCIPLINE[source] not in {
            Discipline.MEDICAL,
            Discipline.PPE,
            Discipline.TRAINING,
        }, source


async def test_просрочки_становятся_событиями_один_раз(sessionmaker, data_factory):
    tenant_id = await _tenant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        overdue = await _driver(
            session, tenant_id, last_name="Просроченный", license_due=TODAY - timedelta(days=10)
        )
        await _driver(
            session, tenant_id, last_name="Годный", license_due=TODAY + timedelta(days=90)
        )
        # отстранённый водитель с истёкшими правами — не срок, а архив
        await _driver(
            session,
            tenant_id,
            last_name="Отстранённый",
            license_due=TODAY - timedelta(days=10),
            status="suspended",
        )
        session.add(
            Vehicle(
                tenant_id=tenant_id,
                plate_number="А001АА77",
                brand_model="ГАЗель",
                kind="truck",
                inspection_due=TODAY - timedelta(days=5),
                insurance_due=TODAY - timedelta(days=3),
                license_due=TODAY + timedelta(days=30),
            )
        )
        session.add_all(
            [
                CivilDefenseDrill(
                    tenant_id=tenant_id,
                    kind="evacuation",
                    title="Эвакуация",
                    planned_on=TODAY - timedelta(days=7),
                ),
                CivilDefenseDrill(  # проведено — протокол, а не срок
                    tenant_id=tenant_id,
                    kind="evacuation",
                    title="Проведённая",
                    planned_on=TODAY - timedelta(days=7),
                    held_on=TODAY - timedelta(days=7),
                ),
            ]
        )
        await session.commit()
        overdue_person = str(overdue.person_id)

    first = await _run(sessionmaker, tenant_id)
    assert first.emitted == 4, first  # права + техосмотр + ОСАГО + учение
    assert first.skipped == (Discipline.INDUSTRIAL_SAFETY, Discipline.ECOLOGY)
    assert first.truncated == ()

    rows = await _events(sessionmaker, tenant_id)
    by_key = {row.idempotency_key: row.payload for row in rows}
    assert len(by_key) == 4
    driver_key = next(k for k in by_key if ":road_safety_driver:" in k)
    payload = by_key[driver_key]
    assert payload["discipline"] == "road_safety"
    assert payload["source_type"] == "road_safety_driver"
    assert payload["days_overdue"] == 10
    assert payload["person_id"] == overdue_person
    assert payload["title"].startswith("Водительское удостоверение: Просроченный")
    assert driver_key.endswith((TODAY - timedelta(days=10)).isoformat())
    # два срока одной машины — два события, вид в ключе и в payload
    vehicle_kinds = sorted(
        p["kind"] for p in by_key.values() if p["source_type"] == "road_safety_vehicle"
    )
    assert vehicle_kinds == ["inspection", "insurance"]
    drill = next(p for p in by_key.values() if p["source_type"] == "civil_defense_drill")
    assert drill["discipline"] == "civil_defense" and drill["days_overdue"] == 7

    second = await _run(sessionmaker, tenant_id)
    assert second.emitted == 0, "тот же день — ничего нового"
    assert len(await _events(sessionmaker, tenant_id)) == 4


async def test_продлённый_и_снова_просроченный_срок_даёт_новое_событие(sessionmaker, data_factory):
    tenant_id = await _tenant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        driver = await _driver(
            session, tenant_id, last_name="Дважды", license_due=TODAY - timedelta(days=30)
        )
        await session.commit()
        driver_id = driver.id

    assert (await _run(sessionmaker, tenant_id)).emitted == 1

    async with sessionmaker() as session:
        row = await session.get(Driver, driver_id)
        row.license_due = TODAY - timedelta(days=1)  # продлили, и снова истекло
        await session.commit()

    assert (await _run(sessionmaker, tenant_id)).emitted == 1
    keys = sorted(r.idempotency_key for r in await _events(sessionmaker, tenant_id))
    assert len(keys) == 2 and keys[0] != keys[1]


async def test_дисциплина_без_модуля_молчит_и_это_названо(sessionmaker, data_factory):
    tenant_id = await _tenant(sessionmaker, data_factory, modules=("road_safety",))
    async with sessionmaker() as session:
        session.add(
            CivilDefenseDrill(
                tenant_id=tenant_id,
                kind="evacuation",
                title="Без модуля",
                planned_on=TODAY - timedelta(days=7),
            )
        )
        await _driver(
            session, tenant_id, last_name="Водитель", license_due=TODAY - timedelta(days=2)
        )
        await session.commit()

    outcome = await _run(sessionmaker, tenant_id)
    assert outcome.emitted == 1, "только БДД: модуль ГО не выдан"
    assert Discipline.CIVIL_DEFENSE in outcome.skipped

    # выдали модуль — учение стало событием на следующем обходе
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.set_modules(session, tenant.id, ("civil_defense",))
        await session.commit()
    outcome = await _run(sessionmaker, tenant_id)
    assert outcome.emitted == 1
    assert Discipline.CIVIL_DEFENSE not in outcome.skipped


async def test_срок_отчётности_эколога_становится_событием_а_исполненный_нет(
    sessionmaker, data_factory
):
    """Срез-72: 2-ТП и платежи (срез-71) — тот же обход, без второй формулы."""

    tenant_id = await _tenant(sessionmaker, data_factory, modules=("ecology",))
    async with sessionmaker() as session:
        session.add_all(
            [
                EcologyReportingDeadline(
                    tenant_id=tenant_id,
                    kind="report",
                    title="2-ТП (воздух)",
                    due_on=TODAY - timedelta(days=6),
                ),
                EcologyReportingDeadline(
                    tenant_id=tenant_id,
                    kind="payment",
                    title="Плата за НВОС, I квартал",
                    due_on=TODAY - timedelta(days=6),
                    done_on=TODAY - timedelta(days=7),
                ),
                EcologyReportingDeadline(
                    tenant_id=tenant_id,
                    kind="payment",
                    title="Плата за НВОС, II квартал",
                    due_on=TODAY + timedelta(days=20),
                ),
            ]
        )
        await session.commit()

    outcome = await _run(sessionmaker, tenant_id)
    assert outcome.emitted == 1, outcome

    rows = await _events(sessionmaker, tenant_id)
    assert len(rows) == 1
    key, payload = rows[0].idempotency_key, rows[0].payload
    assert ":ecology_report:" in key and ":report:" in key, key
    assert key.endswith((TODAY - timedelta(days=6)).isoformat())
    assert payload["discipline"] == "ecology"
    assert payload["source_type"] == "ecology_report"
    assert payload["kind"] == "report"
    assert payload["title"] == "Отчётность: 2-ТП (воздух)"
    assert payload["days_overdue"] == 6

    assert (await _run(sessionmaker, tenant_id)).emitted == 0, "тот же день — ничего нового"


async def test_без_единого_модуля_обход_пуст(sessionmaker, data_factory):
    tenant_id = await _tenant(sessionmaker, data_factory, modules=())
    async with sessionmaker() as session:
        await _driver(session, tenant_id, last_name="Никому", license_due=TODAY - timedelta(days=2))
        await session.commit()

    outcome = await _run(sessionmaker, tenant_id)
    assert outcome.emitted == 0
    assert Discipline.ROAD_SAFETY in outcome.skipped
    assert await _events(sessionmaker, tenant_id) == []


async def test_окно_как_у_центра_внимания(sessionmaker, data_factory):
    """Просрочка старше полугода — архив: первый обход не завалит задачами."""

    tenant_id = await _tenant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        await _driver(
            session, tenant_id, last_name="Архив", license_due=TODAY - timedelta(days=200)
        )
        await _driver(session, tenant_id, last_name="Свежий", license_due=TODAY - timedelta(days=1))
        await session.commit()

    outcome = await _run(sessionmaker, tenant_id)
    assert outcome.emitted == 1
    (row,) = await _events(sessionmaker, tenant_id)
    assert "Свежий" in row.payload["title"]


async def test_потолок_обхода_назван(sessionmaker, data_factory, monkeypatch):
    tenant_id = await _tenant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        for i in range(3):
            await _driver(
                session,
                tenant_id,
                last_name=f"Водитель{i}",
                license_due=TODAY - timedelta(days=i + 1),
            )
        await session.commit()
    monkeypatch.setattr(svc, "DEADLINE_EVENTS_LIMIT", 2)

    outcome = await _run(sessionmaker, tenant_id)

    assert outcome.emitted == 2
    assert outcome.truncated == ("road_safety_driver",)


def test_ключ_события_вычисляется_из_payload() -> None:
    """Ключ из payload и ключ обхода — один и тот же: иначе повтор события
    через другую ручку (вебхук-тест, ручной enqueue) плодил бы дубли."""

    from app.services.events import (
        DisciplineDeadlineOverduePayload,
        dedupe_key_for,
        discipline_deadline_key,
    )

    payload = DisciplineDeadlineOverduePayload(
        tenant_id="t",
        discipline="road_safety",
        source_type="road_safety_vehicle",
        source_id="v1",
        title="Техосмотр ТС: А001АА77",
        due_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        kind="inspection",
    )
    assert dedupe_key_for(
        EventType.DISCIPLINE_DEADLINE_OVERDUE, payload
    ) == discipline_deadline_key(
        source_type="road_safety_vehicle",
        source_id="v1",
        kind="inspection",
        due_on=date(2026, 8, 1),
    )
    assert dedupe_key_for(EventType.DISCIPLINE_DEADLINE_OVERDUE, payload).endswith(
        ":inspection:2026-08-01"
    )
