"""BIZ-54-57 срез-4: библиотека правил живьём (Доп. №1 разд. 57.3).

Правила библиотеки проверены построчно в ``tests/test_rules_library.py``; здесь
— то, что видно только на настоящей связке:

* выдача наряда-допуска на огневые работы ДОХОДИТ до движка и создаёт задачу
  (событие → outbox → правило → задача). Без этой проверки библиотека могла бы
  быть безупречной на бумаге и молчать в жизни;
* правило другой дисциплины на этом же событии НЕ срабатывает — вид работ
  разделяет ПБ и ПромБез, иначе «дисциплина» была бы украшением;
* повторная выдача библиотеки не плодит копий;
* каталог библиотеки называет дисциплины без правил ПРИЧИНОЙ, а не нулём;
* (срез-62) просроченные права водителя доходят до задачи — и ровно одной;
* (срез-63) ручка выдачи даёт существующему арендатору недостающие правила,
  не возвращает удалённые специалистом и доступна только admin/owner;
* (срез-72) пропущенный срок 2-ТП доходит до задачи эколога — и ровно одной;
  исполненный срок задачи не рождает;
* (срез-76) истёкшее удостоверение по обучению доходит до задачи
  «направить на переобучение» — и ровно одной, без покупки модуля: обучение —
  ядро. Счёт правил — 14.
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
    assert body["total"] == 14
    assert body["installed"] == 14
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


@pytest.mark.asyncio
async def test_пропущенный_срок_отчётности_доходит_до_задачи_и_один_раз(
    tenant_with_library, sessionmaker, data_factory
):
    """Срез-72 живьём: срок 2-ТП (срез-71) → обход → событие → правило → задача.

    Исполненный срок с прошедшей датой задачи не рождает — календарь его не
    отдаёт (срез-71), а значит, и событию взяться неоткуда.
    """

    from datetime import date, timedelta

    from app.models.ecology import EcologyReportingDeadline
    from app.services.discipline_deadline_events import emit_overdue_deadline_events

    tenant, _ = tenant_with_library
    tid = str(tenant.id)
    async with sessionmaker() as session:
        await data_factory.set_modules(session, tenant.id, ("ecology",))
        session.add_all(
            [
                EcologyReportingDeadline(
                    tenant_id=tid,
                    kind="report",
                    title="2-ТП (отходы) за прошлый год",
                    due_on=date.today() - timedelta(days=4),
                ),
                EcologyReportingDeadline(
                    tenant_id=tid,
                    kind="payment",
                    title="Плата за НВОС за прошлый год",
                    due_on=date.today() - timedelta(days=4),
                    done_on=date.today() - timedelta(days=5),
                ),
            ]
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
    matching = [t for t in titles if "сдать и отметить исполнение" in t]
    assert len(matching) == 1, titles
    assert matching[0].startswith("Отчётность: 2-ТП (отходы)")
    # исполненный платёж задачи не родил; правила других источников молчат
    assert not any("Плата за НВОС" in t for t in titles), titles
    assert not any("переоформить разрешение" in t or "провести замер" in t for t in titles), titles


@pytest.mark.asyncio
async def test_истёкшее_удостоверение_доходит_до_задачи_и_один_раз(
    tenant_with_library, sessionmaker
):
    """Срез-76 живьём: срок удостоверения (срез-75) → обход → событие → правило → задача.

    Обучение — ядро: модуль не нужен. Действующее удостоверение задачи не
    рождает; повторный обход в тот же день — второй задачи нет.
    """

    from datetime import date, timedelta

    from app.models.master_data import Person
    from app.models.models import Company, TrainingCertificate, TrainingProgram
    from app.services.discipline_deadline_events import emit_overdue_deadline_events

    tenant, _ = tenant_with_library
    tid = str(tenant.id)
    async with sessionmaker() as session:
        company = Company(tenant_id=tid, name="ООО Стройка")
        program = TrainingProgram(
            tenant_id=tid, code="ОТ-1", title="Охрана труда", category="ot", kind="program"
        )
        session.add_all([company, program])
        await session.flush()
        person = Person(
            tenant_id=tid, company_id=company.id, first_name="Анна", last_name="Смирнова"
        )
        session.add(person)
        await session.flush()
        session.add_all(
            [
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-1",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=date.today() - timedelta(days=370),
                    valid_until=date.today() - timedelta(days=3),
                ),
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-2",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=date.today() - timedelta(days=10),
                    valid_until=date.today() + timedelta(days=355),
                ),
            ]
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
    matching = [t for t in titles if "направить на переобучение" in t]
    assert len(matching) == 1, titles
    assert matching[0].startswith("Удостоверение: Охрана труда — Смирнова Анна")
    # правила других источников на том же событии молчат
    assert not any("отстранить от рейсов" in t or "ЭПБ" in t for t in titles), titles


@pytest.mark.asyncio
async def test_выдача_недостающих_правил_существующему_арендатору(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    """Срез-63: арендатор, созданный до пополнения библиотеки, получает правила ручкой.

    Первая выдача заводит всё; вторая — ничего не плодит и честно говорит
    «создано 0». Каталог после выдачи показывает «выдано 14 из 14».
    """

    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    before = await async_client.get(f"{RULES}/library", headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["installed"] == 0

    first = await async_client.post(f"{RULES}/library/install", headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert len(body["created"]) == body["total"] == 14
    assert body["installed"] == 14
    assert body["kept_deleted"] == []
    assert any("отстранить от рейсов" in name or "БДД" in name for name in body["created"])

    second = await async_client.post(f"{RULES}/library/install", headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["created"] == []
    assert second.json()["installed"] == 14

    after = await async_client.get(f"{RULES}/library", headers=headers)
    assert after.json()["installed"] == 14
    assert after.json()["removed"] == 0
    # срез-66: до выдачи каждая строка называла имена по своей дисциплине,
    # после — не выдано нечего
    rows_before = {row["discipline"]: row for row in before.json()["items"]}
    assert rows_before["road_safety"]["missing"] == [
        name for name in body["created"] if "БДД" in name or "рейс" in name
    ]
    assert sum(len(row["missing"]) for row in rows_before.values()) == 14
    assert all(row["missing"] == [] for row in after.json()["items"])
    assert all(row["removed"] == [] for row in after.json()["items"])


@pytest.mark.asyncio
async def test_удалённое_специалистом_правило_не_возвращается(
    async_client, make_auth_headers, tenant_with_library, sessionmaker
):
    """Срез-63: удаление — решение специалиста, выдача его не отменяет.

    Имя правила уникально на арендатора БЕЗ учёта удалённых, поэтому старый
    посев «по живым именам» упёрся бы здесь в ограничение базы. Теперь
    удалённое называется в ответе отдельно, а посев при создании арендатора
    (``seed_rule_library``) на том же арендаторе тоже не падает.
    """

    from app.models.rules_engine import AutomationRule

    tenant, _ = tenant_with_library
    headers = await make_auth_headers(RoleEnum.ADMIN)

    async with sessionmaker() as session:
        rule_id, name = (
            await session.execute(
                select(AutomationRule.id, AutomationRule.name)
                .where(AutomationRule.tenant_id == str(tenant.id))
                .order_by(AutomationRule.name)
                .limit(1)
            )
        ).one()
    deleted = await async_client.delete(f"{RULES}/{rule_id}", headers=headers)
    assert deleted.status_code in (200, 204), deleted.text

    response = await async_client.post(f"{RULES}/library/install", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == []
    assert body["kept_deleted"] == [name]
    assert body["installed"] == 13

    catalog = await async_client.get(f"{RULES}/library", headers=headers)
    assert catalog.json()["installed"] == 13
    assert catalog.json()["removed"] == 1
    # срез-66: удалённое названо по имени в своей строке и НЕ числится «не выданным»
    rows = [row for row in catalog.json()["items"] if row["removed"]]
    assert len(rows) == 1
    assert rows[0]["removed"] == [name]
    assert all(row["missing"] == [] for row in catalog.json()["items"])

    async with sessionmaker() as session:
        assert await seed_rule_library(session, tenant_id=str(tenant.id)) == 0
        await session.commit()


@pytest.mark.asyncio
async def test_выдачу_библиотеки_делает_только_админ(
    async_client, make_auth_headers, tenant_with_library
):
    """Правила исполняют действия от имени системы — выдаёт их только admin/owner."""

    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(f"{RULES}/library/install", headers=headers)

    assert response.status_code == 403, response.text
