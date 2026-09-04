"""Авто-отчёт о состоянии по дисциплинам для арендатора (Доп. №1 разд. 57.4, срез-50).

ТЗ: «авто-отчёты о состоянии по каждой дисциплине (для клиента при аренде)».
Здесь закрепляется, что отчёт говорит ТО ЖЕ, что дашборд, и честно про
динамику:

- строка на каждую дисциплину словаря, числа равны разрезу «по дисциплинам»;
- «не считается» доезжает до отчёта как ``null``, а не как ноль;
- один отчёт на дату: второй запуск в тот же день отдаёт тот же отчёт;
- «хуже/лучше» — только к предыдущему отчёту, с его датой; первый отчёт
  говорит «сравнивать не с чем»;
- список — свежие сверху; роли без аналитики не видят и не собирают.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.models import Company, Incident, IncidentStatus, RoleEnum, Site
from app.services.discipline_attention import ATTENTION_DISCIPLINES
from app.services.discipline_report import (
    build_discipline_report,
    list_reports,
    run_discipline_report,
)
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)
BASE = "/api/v1/analytics/discipline-reports"
BREAKDOWN = "/api/v1/analytics/dashboard/breakdown?dimension=discipline"

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
    """Два открытых ДТП, разлив (экология), неразмеченное, закрытое; три
    просроченных медосмотра."""

    today = date.today()
    await _grant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Отчёт")
        session.add(company)
        await session.flush()
        site = Site(tenant_id=tid, company_id=company.id, name="Склад")
        session.add(site)
        await session.flush()

        def incident(title: str, *, discipline: str | None, **extra):
            return Incident(
                tenant_id=tid,
                company_id=company.id,
                site_id=site.id,
                title=title,
                occurred_at=NOW - timedelta(days=2),
                discipline=discipline,
                **extra,
            )

        person = Person(tenant_id=tid, company_id=company.id, first_name="Пётр", last_name="Ждущий")
        session.add(person)
        await session.flush()
        session.add_all(
            [
                incident("ДТП у ворот", discipline=Discipline.ROAD_SAFETY.value),
                incident("Наезд на складе", discipline=Discipline.ROAD_SAFETY.value),
                incident("Разлив масла", discipline=Discipline.ECOLOGY.value),
                incident("Порез при уборке", discipline=None),
                incident(
                    "Старое ДТП",
                    discipline=Discipline.ROAD_SAFETY.value,
                    status=IncidentStatus.CLOSED,
                ),
                *[
                    MedicalExam(
                        tenant_id=tid,
                        person_id=person.id,
                        exam_type="периодический",
                        exam_date=today - timedelta(days=400),
                        valid_until=today - timedelta(days=35 + shift),
                    )
                    for shift in range(3)
                ],
            ]
        )
        await session.commit()
        return tid


def _rows(report: dict) -> dict[str, dict]:
    return {row["discipline"]: row for row in report["payload"]["rows"]}


@pytest.mark.asyncio
async def test_собрать_сейчас_снимок_равен_разрезу_и_строка_на_каждую_дисциплину(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(f"{BASE}/run", headers=headers)
    breakdown = {
        row["id"]: row
        for row in (await async_client.get(BREAKDOWN, headers=headers)).json()["items"]
    }

    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["created"] is True
    report = body["report"]
    assert report["period_end"] == date.today().isoformat()
    rows = _rows(report)
    # строка на КАЖДУЮ дисциплину словаря, словами словаря — и те же числа,
    # что видит директор в разрезе (одна формула, а не второй расчёт)
    assert set(rows) == {d.value for d in Discipline}
    for discipline in Discipline:
        row, seen = rows[discipline.value], breakdown[discipline.value]
        assert row["title"] == DISCIPLINE_TITLES[discipline]
        assert row["incidents_open"] == seen["incidents_open"]
        assert row["overdue_items"] == seen["overdue_items"]
        assert row["total_issues"] == seen["total_issues"]
        if discipline not in ATTENTION_DISCIPLINES:
            assert row["overdue_items"] is None, "«не считается» — не ноль"
    assert rows["road_safety"]["incidents_open"] == 2
    assert rows["medical"]["overdue_items"] == 3
    # неразмеченное — отдельным числом, а не строкой дисциплины
    payload = report["payload"]
    assert payload["unmarked_incidents"] == 1
    assert payload["totals"] == {
        "incidents_open": 4,
        "overdue_items": 3,
        "total_issues": 7,
        "previous_total_issues": None,
        "delta": None,
    }
    assert report["total_issues"] == 7
    assert payload["worst"]["discipline"] == "medical"
    # первый отчёт: динамику не выдумываем
    assert "первый отчёт — сравнивать не с чем" in report["summary"]
    assert (
        f"Хуже всего: {DISCIPLINE_TITLES[Discipline.MEDICAL]} — 3 просрочки." in report["summary"]
    )
    assert "Не размечено дисциплиной: 1 происшествие" in report["summary"]
    assert any(action.startswith("Разметить дисциплиной") for action in payload["actions"])
    assert payload["not_applicable"] is None
    assert "Вне редакции" not in report["summary"]


@pytest.mark.asyncio
async def test_дисциплины_вне_редакции_в_отчёте_названы_а_факты_остаются(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    """BIZ-54-57 срез-56: отчёт наследует правило разреза — пустая скрытая строка
    убрана, строка с происшествием остаётся, скрытое названо предложением."""

    await _seed(sessionmaker, data_factory)
    await _grant(sessionmaker, data_factory, ("ecology", "civil_defense"), on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    report = (await async_client.post(f"{BASE}/run", headers=headers)).json()["report"]

    rows = _rows(report)
    assert "civil_defense" not in rows
    assert rows["ecology"]["incidents_open"] == 1
    assert report["total_issues"] == 7, "итог тот же: факты не спрятаны"
    phrase = (
        "Вне редакции арендатора (модуль не выдан или выключен): ГО и ЧС; "
        "Экология — модуль не выдан или выключен, но открытые записи есть и показаны как факты"
    )
    assert report["payload"]["not_applicable"] == phrase
    assert f"{phrase}." in report["summary"]
    assert "Экология: 1 происшествие" in report["summary"]


@pytest.mark.asyncio
async def test_второй_запуск_в_тот_же_день_отдаёт_тот_же_отчёт(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = (await async_client.post(f"{BASE}/run", headers=headers)).json()
    second = (await async_client.post(f"{BASE}/run", headers=headers)).json()
    page = (await async_client.get(BASE, headers=headers)).json()

    assert first["created"] is True
    assert second["created"] is False
    assert second["report"]["id"] == first["report"]["id"]
    assert "уже есть" in second["summary"]
    assert page["total"] == 1
    assert [row["id"] for row in page["items"]] == [first["report"]["id"]]


@pytest.mark.asyncio
async def test_динамика_к_прошлому_отчёту_с_его_датой(sessionmaker, data_factory):
    """Пустой вчера → нарушения сегодня → «хуже»; закрыли → завтра «лучше»."""

    today = date.today()
    # редакция «всё включено» с самого начала: иначе у вчерашнего отчёта не было
    # бы строки БДД, и динамика по ней сегодня честно осталась бы пустой
    await _grant(sessionmaker, data_factory)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        empty = await run_discipline_report(session, tid, today=today - timedelta(days=1))
        await session.commit()
    assert empty.created
    assert empty.report.total_issues == 0
    assert "Нарушений по учтённым источникам не найдено" in empty.report.summary
    assert "Действий не требуется" in empty.report.summary

    await _seed(sessionmaker, data_factory)
    async with sessionmaker() as session:
        worse = await run_discipline_report(session, tid, today=today)
        await session.commit()
    assert worse.created
    assert worse.report.payload["totals"]["previous_total_issues"] == 0
    assert worse.report.payload["totals"]["delta"] == 7
    assert worse.report.payload["previous_period_end"] == (today - timedelta(days=1)).isoformat()
    assert (
        f"в отчёте за {(today - timedelta(days=1)).strftime('%d.%m.%Y')} было 0, хуже на 7"
        in worse.report.summary
    )
    assert _rows_of(worse.report)["road_safety"]["delta"] == 2

    async with sessionmaker() as session:
        accident = (
            await session.execute(select(Incident).where(Incident.title == "ДТП у ворот"))
        ).scalar_one()
        accident.status = IncidentStatus.CLOSED
        await session.commit()
    async with sessionmaker() as session:
        better = await run_discipline_report(session, tid, today=today + timedelta(days=1))
        await session.commit()
        reports, total = await list_reports(session, tid, limit=10)
    assert better.report.payload["totals"]["delta"] == -1
    assert "лучше на 1" in better.report.summary
    assert _rows_of(better.report)["road_safety"]["delta"] == -1
    # свежие сверху, все три на месте
    assert total == 3
    assert [r.period_end for r in reports] == [
        today + timedelta(days=1),
        today,
        today - timedelta(days=1),
    ]


def _rows_of(report) -> dict[str, dict]:
    return {row["discipline"]: row for row in report.payload["rows"]}


@pytest.mark.asyncio
async def test_список_с_лимитом_и_роли_без_аналитики(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    today = date.today()
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        for shift in (3, 1, 2):
            await run_discipline_report(session, tid, today=today - timedelta(days=shift))
        await session.commit()
    admin = await make_auth_headers(RoleEnum.ADMIN)
    worker = await make_auth_headers(RoleEnum.WORKER)

    page = (await async_client.get(f"{BASE}?limit=2", headers=admin)).json()
    denied_list = await async_client.get(BASE, headers=worker)
    denied_run = await async_client.post(f"{BASE}/run", headers=worker)

    assert page["total"] == 3
    assert [row["period_end"] for row in page["items"]] == [
        (today - timedelta(days=1)).isoformat(),
        (today - timedelta(days=2)).isoformat(),
    ]
    assert denied_list.status_code == status.HTTP_403_FORBIDDEN
    assert denied_run.status_code == status.HTTP_403_FORBIDDEN


def test_сборка_без_базы_склонения_и_без_изменений():
    rows = [
        {
            "id": "medical",
            "name": "Медосмотры",
            "incidents_open": 1,
            "overdue_items": 5,
            "total_issues": 6,
        },
        {
            "id": "fire_safety",
            "name": "Пожарная безопасность",
            "incidents_open": 0,
            "overdue_items": None,
            "total_issues": 0,
        },
        {
            "id": "",
            "name": "— не размечено",
            "incidents_open": 11,
            "overdue_items": None,
            "total_issues": 11,
        },
    ]
    previous = {
        "period": {"start": "2026-08-21", "end": "2026-08-28"},
        "rows": [{"discipline": "medical", "total_issues": 6}],
        "totals": {"total_issues": 17},
    }

    content = build_discipline_report(
        period_start=date(2026, 8, 28), period_end=date(2026, 9, 4), rows=rows, previous=previous
    )

    assert content.total_issues == 17
    assert "в отчёте за 28.08.2026 было 17, без изменений" in content.summary
    assert "Хуже всего: Медосмотры — 1 происшествие, 5 просрочек." in content.summary
    assert "Не размечено дисциплиной: 11 происшествий" in content.summary
    assert content.payload["rows"][0]["delta"] == 0
    # у дисциплины, которой в прошлом отчёте не было, динамики нет — не ноль
    assert content.payload["rows"][1]["previous_total_issues"] is None
    assert content.payload["rows"][1]["delta"] is None
    assert content.payload["rows"][1]["overdue_items"] is None
