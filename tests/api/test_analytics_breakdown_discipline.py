"""Разрез «по дисциплинам» на управленческом дашборде (Доп. №1 разд. 57.4, срез-48).

Директору нужен один взгляд на всю безопасность предприятия, а не восемь
экранов контуров. Здесь проверяется, что разрез говорит правду тем же языком,
что и остальной продукт:

- строка есть у КАЖДОЙ дисциплины общего словаря, даже пустой;
- происшествия считаются по разметке, неразмеченные — отдельной строкой, а не
  «охраной труда»;
- просрочки — ТЕ ЖЕ числа, что в Центре внимания (одна формула на двоих);
- где просрочка не считается, там ``None``, а не ноль.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.models import Company, Incident, IncidentStatus, RoleEnum, Site
from app.services.discipline_attention import ATTENTION_DISCIPLINES
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)
BASE = "/api/v1/analytics/dashboard/breakdown"

#: Пять дисциплин Доп. №1 — продаваемые модули; по умолчанию у арендатора
#: теста они НЕ выданы (BIZ-61), и пустых строк по ним в разрезе нет (срез-56).
DISCIPLINE_MODULES = (
    "fire_safety",
    "industrial_safety",
    "ecology",
    "civil_defense",
    "road_safety",
)


async def _grant(sessionmaker, data_factory: TestDataFactory, codes=DISCIPLINE_MODULES, *, on=True):
    """Редакция «всё включено»: иначе в разрезе остались бы три дисциплины ядра."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.set_modules(session, tenant.id, codes, on=on)
        await session.commit()


async def _seed(sessionmaker, data_factory: TestDataFactory) -> str:
    """Три происшествия по дисциплинам, одно без разметки, одно закрытое."""

    await _grant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Разрез")
        session.add(company)
        await session.flush()
        site = Site(tenant_id=tid, company_id=company.id, name="Гараж")
        session.add(site)
        await session.flush()

        def incident(title: str, *, discipline: str | None, days_ago: int = 2, **extra):
            return Incident(
                tenant_id=tid,
                company_id=company.id,
                site_id=site.id,
                title=title,
                occurred_at=NOW - timedelta(days=days_ago),
                discipline=discipline,
                **extra,
            )

        session.add_all(
            [
                incident("ДТП у ворот", discipline=Discipline.ROAD_SAFETY.value),
                incident("Наезд на складе", discipline=Discipline.ROAD_SAFETY.value, days_ago=40),
                incident("Разлив масла", discipline=Discipline.ECOLOGY.value),
                incident("Порез при уборке", discipline=None),
                # закрытое не считается, какой бы дисциплины ни было
                incident(
                    "Старое ДТП",
                    discipline=Discipline.ROAD_SAFETY.value,
                    status=IncidentStatus.CLOSED,
                ),
            ]
        )
        await session.commit()
        return tid


def _by_id(body: dict) -> dict[str, dict]:
    return {row["id"]: row for row in body["items"]}


@pytest.mark.asyncio
async def test_строка_на_каждую_дисциплину_и_неразмеченные_отдельно(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.get(f"{BASE}?dimension=discipline", headers=headers)

    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["dimension"] == "discipline"
    rows = _by_id(body)
    # все восемь дисциплин словаря, словами из того же словаря — даже пустые
    for discipline in Discipline:
        assert rows[discipline.value]["name"] == DISCIPLINE_TITLES[discipline]
    assert rows[Discipline.ROAD_SAFETY.value]["incidents_open"] == 2
    assert rows[Discipline.ECOLOGY.value]["incidents_open"] == 1
    assert rows[Discipline.FIRE_SAFETY.value]["incidents_open"] == 0
    # неразмеченное — своей строкой, а НЕ в какой-либо дисциплине
    unmarked = rows[""]
    assert unmarked["name"] == "— не размечено"
    assert unmarked["incidents_open"] == 1
    assert unmarked["overdue_items"] is None
    assert body["total"] == len(Discipline) + 1
    # худшее сверху: БДД с двумя происшествиями — первая строка
    assert body["items"][0]["id"] == Discipline.ROAD_SAFETY.value


@pytest.mark.asyncio
async def test_без_неразмеченных_строки_нет_и_порядок_словаря(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    """Пустой арендатор: строки словаря в его порядке, синтетической строки нет."""

    await _grant(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    body = (await async_client.get(f"{BASE}?dimension=discipline", headers=headers)).json()

    assert [row["id"] for row in body["items"]] == [d.value for d in Discipline]
    assert all(row["total_issues"] == 0 for row in body["items"])
    assert body["not_applicable"] is None


@pytest.mark.asyncio
async def test_дисциплины_вне_редакции_пустые_скрыты_а_с_фактами_остаются(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    """BIZ-54-57 срез-56, приёмка §58.3: модуль выключен — пустой строки нет,
    строка с открытыми происшествиями остаётся (факт), скрытое названо."""

    await _seed(sessionmaker, data_factory)
    await _grant(sessionmaker, data_factory, ("ecology", "civil_defense"), on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    body = (await async_client.get(f"{BASE}?dimension=discipline", headers=headers)).json()

    rows = _by_id(body)
    assert "civil_defense" not in rows, "пусто и вне редакции — строки нет"
    assert rows["ecology"]["incidents_open"] == 1, "разлив — факт, строка остаётся"
    assert body["total"] == len(Discipline)  # семь дисциплин + «не размечено»
    assert body["not_applicable"] == (
        "Вне редакции арендатора (модуль не выдан или выключен): ГО и ЧС; "
        "Экология — модуль не выдан или выключен, но открытые записи есть и показаны как факты"
    )


@pytest.mark.asyncio
async def test_просрочка_не_считается_это_none_а_не_ноль(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _grant(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    rows = _by_id((await async_client.get(f"{BASE}?dimension=discipline", headers=headers)).json())

    for discipline in Discipline:
        value = rows[discipline.value]["overdue_items"]
        if discipline in ATTENTION_DISCIPLINES:
            assert isinstance(value, int), discipline
        else:
            assert (
                value is None
            ), f"{discipline}: нет размеченных сроков — не ноль, а «не считается»"
    # словарь размеченных не выродился: ПромБез и БДД сроков не имеют, медосмотры имеют
    assert Discipline.MEDICAL in ATTENTION_DISCIPLINES
    assert Discipline.INDUSTRIAL_SAFETY not in ATTENTION_DISCIPLINES


@pytest.mark.asyncio
async def test_просрочки_те_же_что_в_центре_внимания(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    """Одна формула на двоих: разрез и Центр внимания называют одно число."""

    today = date.today()
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Медосмотры")
        session.add(company)
        await session.flush()
        person = Person(
            tenant_id=tid, company_id=company.id, first_name="Пётр", last_name="Просроченный"
        )
        session.add(person)
        await session.flush()
        session.add_all(
            [
                MedicalExam(
                    tenant_id=tid,
                    person_id=person.id,
                    exam_type="периодический",
                    exam_date=today - timedelta(days=400),
                    valid_until=today - timedelta(days=35 + shift),
                )
                for shift in range(3)
            ]
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    attention = (await async_client.get("/api/v1/workspace/attention", headers=headers)).json()
    rows = _by_id((await async_client.get(f"{BASE}?dimension=discipline", headers=headers)).json())

    medical_attention = next(d for d in attention["disciplines"] if d["code"] == "medical")
    assert medical_attention["overdue"] == 3
    assert rows["medical"]["overdue_items"] == medical_attention["overdue"]
    assert rows["medical"]["total_issues"] == 3


@pytest.mark.asyncio
async def test_окно_дат_сужает_происшествия_но_не_просрочки(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    date_from = (NOW - timedelta(days=7)).date().isoformat()

    rows = _by_id(
        (
            await async_client.get(
                f"{BASE}?dimension=discipline&date_from={date_from}", headers=headers
            )
        ).json()
    )

    # 40-дневное ДТП отфильтровано, свежее осталось
    assert rows[Discipline.ROAD_SAFETY.value]["incidents_open"] == 1
    # просрочки описывают «сегодня», окно к ним не применяется — ключ на месте
    assert "overdue_items" in rows[Discipline.MEDICAL.value]
