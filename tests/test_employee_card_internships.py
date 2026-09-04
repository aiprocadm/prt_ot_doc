"""Стажировки в карточке сотрудника (срез-45).

Реестр стажировок общий (``/internships``), а на человеке их не было видно:
агрегат ``/employees/{id}`` собирал обучение из сессий и удостоверений и
о стажировках не знал. Здесь проверяется, что карточка показывает ТУ ЖЕ
запись, что реестр, — без своей копии и своих правил:

- стажировки человека видны на вкладке обучения со словами (состояние,
  дисциплина, наставник);
- недобор считается ТЕМ ЖЕ правилом, что реестр — сравнивается с ручкой
  ``/internships`` напрямую;
- чужие и удалённые не попадают, счётчик считает по базе, а не по списку;
- экспорт персональных данных получает стажировки вместе с карточкой и
  честно помечает усечение.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.disciplines import Discipline
from app.models.master_data import Company, Person
from app.models.models import RoleEnum, Tenant
from app.models.training import Internship
from app.modules.privacy.service import PdnSubjectExportService
from app.services.employee_card import EmployeeCardService

_API = "/api/v1"


async def _person(sessionmaker, last_name: str) -> str:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        company = (
            await session.execute(select(Company).where(Company.tenant_id == tenant.id).limit(1))
        ).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=str(tenant.id), name="ООО «Тест»")
            session.add(company)
            await session.flush()
        person = Person(
            tenant_id=str(tenant.id),
            company_id=company.id,
            last_name=last_name,
            first_name="Пётр",
            middle_name="Иванович",
        )
        session.add(person)
        await session.commit()
        return person.id


async def _internship(
    async_client: AsyncClient,
    headers,
    person_id: str,
    *,
    mentor_id: str | None = None,
    discipline: str | None = None,
    planned: int = 4,
    completed: int = 0,
    status: str = "planned",
    subject: str | None = "стропальщик",
    started_on: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "person_id": person_id,
        "planned_shifts": planned,
        "completed_shifts": completed,
        "status": status,
    }
    if mentor_id is not None:
        payload["mentor_person_id"] = mentor_id
    if discipline is not None:
        payload["discipline"] = discipline
    if subject is not None:
        payload["subject"] = subject
    if started_on is not None:
        payload["started_on"] = started_on
    response = await async_client.post(f"{_API}/internships", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _card(async_client: AsyncClient, headers, person_id: str) -> dict:
    response = await async_client.get(f"{_API}/employees/{person_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
class TestВидныНаЧеловеке:
    async def test_стажировка_видна_словами(self, async_client, make_auth_headers, sessionmaker):
        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Стажёров")
        mentor = await _person(sessionmaker, "Наставников")
        await _internship(
            async_client,
            headers,
            trainee,
            mentor_id=mentor,
            discipline=Discipline.ROAD_SAFETY.value,
            planned=5,
            completed=5,
            status="completed",
            subject="автобус категории D",
        )

        training = (await _card(async_client, headers, trainee))["training"]

        assert training["internships_count"] == 1
        (item,) = training["internships"]
        assert item["subject"] == "автобус категории D"
        assert item["status_label"] == "Завершена"
        assert item["discipline_label"] == "БДД"
        assert item["mentor_name"] == "Наставников Пётр Иванович"
        assert item["completed_short"] is False

    async def test_без_наставника_и_разметки_пусто_а_не_неизвестно(
        self, async_client, make_auth_headers, sessionmaker
    ):
        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Одинов")
        await _internship(async_client, headers, trainee)

        (item,) = (await _card(async_client, headers, trainee))["training"]["internships"]

        assert item["mentor_name"] is None
        assert item["discipline"] is None
        assert item["discipline_label"] is None
        assert item["status_label"] == "Назначена"

    async def test_без_стажировок_ноль_и_пустой_список(
        self, async_client, make_auth_headers, sessionmaker
    ):
        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Пустов")

        training = (await _card(async_client, headers, trainee))["training"]

        assert training["internships_count"] == 0
        assert training["internships"] == []


@pytest.mark.anyio
class TestТоЖеПравилоЧтоРеестр:
    async def test_недобор_совпадает_с_реестром(
        self, async_client, make_auth_headers, sessionmaker
    ):
        """Завершена, а смен меньше плана — недобор; карточка и реестр говорят одно."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Недоборов")
        short = await _internship(
            async_client, headers, trainee, planned=5, completed=3, status="completed"
        )
        cancelled = await _internship(
            async_client, headers, trainee, planned=5, completed=1, status="cancelled"
        )

        registry = {
            row["id"]: row
            for row in (
                await async_client.get(
                    f"{_API}/internships", params={"person_id": trainee}, headers=headers
                )
            ).json()["items"]
        }
        card_items = {
            row["id"]: row
            for row in (await _card(async_client, headers, trainee))["training"]["internships"]
        }

        assert card_items[short["id"]]["completed_short"] is True
        # отменённая с недобором смен — НЕ недобор: её не завершали
        assert card_items[cancelled["id"]]["completed_short"] is False
        for internship_id in (short["id"], cancelled["id"]):
            assert (
                card_items[internship_id]["completed_short"]
                == registry[internship_id]["completed_short"]
            )
            assert (
                card_items[internship_id]["status_label"] == registry[internship_id]["status_label"]
            )

    async def test_свежие_сверху_без_даты_в_конце(
        self, async_client, make_auth_headers, sessionmaker
    ):
        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Порядков")
        old = await _internship(async_client, headers, trainee, started_on="2025-01-10")
        undated = await _internship(async_client, headers, trainee)
        fresh = await _internship(async_client, headers, trainee, started_on="2026-03-01")

        items = (await _card(async_client, headers, trainee))["training"]["internships"]

        assert [row["id"] for row in items] == [fresh["id"], old["id"], undated["id"]]


@pytest.mark.anyio
class TestГраницы:
    async def test_чужие_и_удалённые_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ):
        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Свойкин")
        other = await _person(sessionmaker, "Чужаков")
        mine = await _internship(async_client, headers, trainee)
        removed = await _internship(async_client, headers, trainee, subject="удалённая")
        await _internship(async_client, headers, other, subject="чужая")

        # ручки удаления у реестра нет (отмена меняет состояние) — мягкое
        # удаление ставится напрямую, как сделал бы сервис очистки
        async with sessionmaker() as session:
            record = await session.get(Internship, removed["id"])
            assert record is not None
            record.deleted_at = datetime.now(timezone.utc)
            await session.commit()

        training = (await _card(async_client, headers, trainee))["training"]

        assert training["internships_count"] == 1
        assert [row["id"] for row in training["internships"]] == [mine["id"]]

    async def test_счётчик_по_базе_а_список_усечён(
        self, async_client, make_auth_headers, sessionmaker
    ):
        """Предел на секцию режет список, но не счётчик — и экспорт ПДн это видит."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        trainee = await _person(sessionmaker, "Многов")
        for _ in range(3):
            await _internship(async_client, headers, trainee)

        async with sessionmaker() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "test"))
            ).scalar_one()
            card = await EmployeeCardService(
                tenant_id=str(tenant.id), db=session, max_items_per_section=2
            ).build(trainee)
            assert card is not None
            assert card.training.internships_count == 3
            assert len(card.training.internships) == 2

            # усечённая секция стажировок помечает экспорт как неполный
            assert PdnSubjectExportService._is_truncated(card) is True

            export = await PdnSubjectExportService(tenant_id=str(tenant.id), session=session).build(
                trainee
            )
            assert export is not None
            assert export.data.training.internships_count == 3
            assert len(export.data.training.internships) == 3
            assert export.truncated is False
