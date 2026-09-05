"""BIZ-54-57 срез-4: библиотека правил живьём (Доп. №1 разд. 57.3).

Правила библиотеки проверены построчно в ``tests/test_rules_library.py``; здесь
— то, что видно только на настоящей связке:

* выдача наряда-допуска на огневые работы ДОХОДИТ до движка и создаёт задачу
  (событие → outbox → правило → задача). Без этой проверки библиотека могла бы
  быть безупречной на бумаге и молчать в жизни;
* правило другой дисциплины на этом же событии НЕ срабатывает — вид работ
  разделяет ПБ и ПромБез, иначе «дисциплина» была бы украшением;
* повторная выдача библиотеки не плодит копий;
* каталог библиотеки называет дисциплины без правил ПРИЧИНОЙ, а не нулём.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import RoleEnum
from app.models.obligations import Task
from app.services.rules_library_seed import seed_rule_library

PERMITS = "/api/v1/work-permits"
RULES = "/api/v1/rules"


@pytest.fixture(autouse=True)
def _module_on(monkeypatch: pytest.MonkeyPatch):
    """Модуль правил куплен: без него движок молчит по построению."""

    from unittest.mock import AsyncMock

    from app.modules.rules_engine import api as rules_api
    from app.modules.rules_engine import engine as rules_engine

    monkeypatch.setattr(rules_api, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(rules_engine, "is_module_enabled", AsyncMock(return_value=True))


@pytest.fixture()
async def tenant_with_library(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        created = await seed_rule_library(session, tenant_id=str(tenant.id))
        await session.commit()
        return tenant, created


@pytest.mark.asyncio
async def test_выдача_наряда_на_огневые_работы_создаёт_задачу_по_пб(
    async_client, make_auth_headers, tenant_with_library, sessionmaker
):
    tenant, _ = tenant_with_library
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(
        PERMITS,
        headers=headers,
        json={"work_type": "hot_work", "zone_text": "Цех 1", "number": "НД-777"},
    )
    assert created.status_code == 201, created.text
    permit_id = created.json()["id"]

    issued = await async_client.post(f"{PERMITS}/{permit_id}/issue", headers=headers, json={})

    assert issued.status_code == 200, issued.text
    async with sessionmaker() as session:
        titles = [
            str(title)
            for title in (
                await session.execute(select(Task.title).where(Task.tenant_id == str(tenant.id)))
            ).scalars()
        ]
    assert any("Огневые работы" in title for title in titles), titles
    # Номер наряда подставился: пустое место вместо номера обесценило бы задачу.
    assert any("НД-777" in title for title in titles), titles


@pytest.mark.asyncio
async def test_правило_промбеза_на_огневой_наряд_не_срабатывает(
    async_client, make_auth_headers, tenant_with_library, sessionmaker
):
    """Вид работ разделяет дисциплины — иначе разметка была бы украшением."""

    tenant, _ = tenant_with_library
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(
        PERMITS,
        headers=headers,
        json={"work_type": "hot_work", "zone_text": "Цех 1", "number": "НД-778"},
    )
    permit_id = created.json()["id"]
    await async_client.post(f"{PERMITS}/{permit_id}/issue", headers=headers, json={})

    async with sessionmaker() as session:
        titles = [
            str(title)
            for title in (
                await session.execute(select(Task.title).where(Task.tenant_id == str(tenant.id)))
            ).scalars()
        ]
    assert not any("Газоопасные" in title for title in titles), titles


@pytest.mark.asyncio
async def test_черновик_наряда_ничего_не_запускает(
    async_client, make_auth_headers, tenant_with_library, sessionmaker
):
    """Черновик — ещё не работа: событие испускается только на выдаче."""

    tenant, _ = tenant_with_library
    headers = await make_auth_headers(RoleEnum.ADMIN)

    await async_client.post(
        PERMITS,
        headers=headers,
        json={"work_type": "hot_work", "zone_text": "Цех 1", "number": "НД-779"},
    )

    async with sessionmaker() as session:
        titles = [
            str(title)
            for title in (
                await session.execute(select(Task.title).where(Task.tenant_id == str(tenant.id)))
            ).scalars()
        ]
    assert not any("Огневые работы" in title for title in titles), titles


@pytest.mark.asyncio
async def test_повторная_выдача_библиотеки_не_плодит_копий(tenant_with_library, sessionmaker):
    tenant, first = tenant_with_library
    assert first > 0, "первая выдача обязана что-то завести"

    async with sessionmaker() as session:
        again = await seed_rule_library(session, tenant_id=str(tenant.id))
        await session.commit()

    assert again == 0


@pytest.mark.asyncio
async def test_каталог_называет_дисциплины_без_правил_причиной(
    async_client, make_auth_headers, tenant_with_library
):
    _tenant, _ = tenant_with_library
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(f"{RULES}/library", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 12
    assert body["installed"] == 12
    rows = {row["discipline"]: row for row in body["items"]}
    assert len(rows) == 8, "в каталоге обязаны быть ВСЕ дисциплины ТЗ"
    assert rows["fire_safety"]["rules"] == 1
    # срез-62: событие сроков закрыло три пустые клетки — причин больше нет,
    # но поле остаётся: пустая клетка без причины по-прежнему запрещена
    for code in ("ecology", "civil_defense", "road_safety"):
        assert rows[code]["rules"] >= 1, code
        assert rows[code]["reason"] == "", code


@pytest.mark.asyncio
async def test_просроченные_права_водителя_доходят_до_задачи_и_один_раз(
    tenant_with_library, sessionmaker, data_factory
):
    """Срез-62 живьём: обход сроков → событие → правило БДД → задача.

    И ровно одна: повторный обход в тот же день события не заводит, а
    значит, и второй задачи «отстранить от рейсов» не будет.
    """

    from datetime import date, timedelta

    from app.models.master_data import Person
    from app.models.models import Company
    from app.models.road_safety import Driver
    from app.services.discipline_deadline_events import emit_overdue_deadline_events

    tenant, _ = tenant_with_library
    tid = str(tenant.id)
    async with sessionmaker() as session:
        await data_factory.set_modules(session, tenant.id, ("road_safety",))
        company = Company(tenant_id=tid, name="ООО Автобаза")
        session.add(company)
        await session.flush()
        person = Person(tenant_id=tid, company_id=company.id, first_name="Иван", last_name="Рулёв")
        session.add(person)
        await session.flush()
        session.add(
            Driver(
                tenant_id=tid,
                person_id=person.id,
                license_number="77 АА 123456",
                categories=["B", "C"],
                license_due=date.today() - timedelta(days=3),
                status="admitted",
            )
        )
        await session.commit()

    for _ in range(2):
        async with sessionmaker() as session:
            await emit_overdue_deadline_events(session, tenant_id=tid)
            await session.commit()

    async with sessionmaker() as session:
        titles = [
            str(title)
            for title in (
                await session.execute(select(Task.title).where(Task.tenant_id == tid))
            ).scalars()
        ]
    matching = [t for t in titles if "отстранить от рейсов" in t]
    assert len(matching) == 1, titles
    assert "Рулёв" in matching[0]
    # правило другой дисциплины на том же событии молчит
    assert not any("ЭПБ" in t or "разрешение" in t for t in titles), titles
