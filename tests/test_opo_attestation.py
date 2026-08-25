"""Контур ПромБез срез-4 (Доп. №1 разд. 54.2): аттестация по промбезопасности.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. ТЗ требует «аттестацию по промбезопасности
персонала (ОБЛАСТИ АТТЕСТАЦИИ), сроки, связь с обучением».

* Сущность аттестации в ядре ЕСТЬ (``Attestation``: человек, должность, даты
  выдачи и окончания, состояние, ответственный) — дублировать её нельзя;
* но **область аттестации — свободная строка ``name``**. Значит вопрос «кто у
  нас аттестован по Б.9 (подъёмные сооружения)» не имел ответа: «Б.9»,
  «Б9», «подъёмные сооружения» и «ПС» — четыре разные строки. Требование ТЗ
  со словом «области» было невыполнимо по построению — то же семейство дыр,
  что свободный вид инструктажа и свободный класс опасности площадки;
* **экрана у аттестаций нет ни одного** — записи существуют только через API,
  человек их нигде не видит (в интерфейсе есть лишь тип задачи «Аттестации»).

Поэтому срез: закрытый справочник областей в ЯДРЕ (рядом с видами инструктажа,
там же живёт разметка дисциплин), необязательное поле ``area_code`` у ядровой
аттестации, валидация НА ЗАПИСИ и видимость в контуре ПромБеза.

ГРАНИЦА: область НЕОБЯЗАТЕЛЬНА. У аттестаций других дисциплин её нет, и
требовать её значило бы сломать существующие записи; промбезовской считается
запись с областью из справочника.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, Person
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/industrial-safety"
_CORE = "/api/v1/attestations"


async def _grant(sessionmaker, code: str = "industrial_safety", on: bool = True) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            grant.on = on
        await session.commit()


async def _person(sessionmaker, last_name: str = "Петров", first_name: str = "Пётр") -> str:
    """Человек с компанией: ``Person.company_id`` — NOT NULL."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = (
            await session.execute(
                select(Company).where(Company.tenant_id == tenant.id).limit(1)
            )
        ).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=str(tenant.id), name="ООО «Тест»")
            session.add(company)
            await session.flush()
        person = Person(
            tenant_id=str(tenant.id),
            company_id=company.id,
            last_name=last_name,
            first_name=first_name,
        )
        session.add(person)
        await session.commit()
        return person.id


class TestОбластьАттестации:
    async def test_область_принимается_и_читается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        person_id = await _person(sessionmaker)
        today = date.today()
        created = await async_client.post(
            _CORE,
            json={
                "person_id": person_id,
                "name": "Аттестация по промышленной безопасности",
                "area_code": "Б.9",
                "issued_at": str(today - timedelta(days=30)),
                "expires_at": str(today + timedelta(days=1795)),
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["area_code"] == "Б.9"
        assert "подъёмные сооружения" in body["area_label"]

    async def test_неизвестная_область_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Дыра свободной строки не повторяется: область — закрытый справочник.

        «Б9», «подъёмные сооружения», «ПС» были бы тремя разными областями, и
        вопрос «кто аттестован по Б.9» снова остался бы без ответа.
        """

        headers = await make_auth_headers()
        person_id = await _person(sessionmaker)
        response = await async_client.post(
            _CORE,
            json={
                "person_id": person_id,
                "name": "Аттестация",
                "area_code": "Б9",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестная область аттестации" in response.text

    async def test_область_необязательна(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: у аттестаций других дисциплин области нет.

        Сделать поле обязательным значило бы сломать существующие записи и
        объявить всякую аттестацию промбезовской.
        """

        headers = await make_auth_headers()
        person_id = await _person(sessionmaker, "Иванов", "Иван")
        response = await async_client.post(
            _CORE,
            json={"person_id": person_id, "name": "Аттестация по электробезопасности"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["area_code"] is None
        assert response.json()["area_label"] is None

    async def test_область_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        person_id = await _person(sessionmaker, "Сидоров", "Сидор")
        created = await async_client.post(
            _CORE,
            json={"person_id": person_id, "name": "Аттестация", "area_code": "Б.8"},
            headers=headers,
        )
        assert created.status_code == 201, created.text
        patched = await async_client.patch(
            f"{_CORE}/{created.json()['id']}",
            json={"area_code": "Б.7"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["area_code"] == "Б.7"
        assert "газораспределения" in patched.json()["area_label"]

    async def test_неизвестная_область_не_проходит_и_правкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        person_id = await _person(sessionmaker, "Кузнецов", "Кузьма")
        created = await async_client.post(
            _CORE,
            json={"person_id": person_id, "name": "Аттестация", "area_code": "А.1"},
            headers=headers,
        )
        response = await async_client.patch(
            f"{_CORE}/{created.json()['id']}",
            json={"area_code": "Х.1"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестная область аттестации" in response.text


class TestВидимостьВКонтуреПромБеза:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/attestations", headers=headers)
        assert response.status_code == 404

    async def test_видны_только_промбезовские_аттестации(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Контур показывает свои записи: аттестация без области — не его.

        До среза аттестации не было видно НИГДЕ: экрана у них нет вовсе,
        только тип задачи в фильтре задач.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        opo_person = await _person(sessionmaker, "Промбез", "Промбезович")
        other_person = await _person(sessionmaker, "Электрик", "Электрикович")
        await async_client.post(
            _CORE,
            json={
                "person_id": opo_person,
                "name": "Аттестация ПБ",
                "area_code": "Б.1",
            },
            headers=headers,
        )
        await async_client.post(
            _CORE,
            json={"person_id": other_person, "name": "Электробезопасность"},
            headers=headers,
        )

        listed = await async_client.get(f"{_API}/attestations", headers=headers)
        assert listed.status_code == 200, listed.text
        names = [item["person_name"] for item in listed.json()["items"]]
        assert "Промбез Промбезович" in names
        assert "Электрик Электрикович" not in names
        assert listed.json()["items"][0]["area_label"]

    async def test_срок_считается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Аттестация действует пять лет; просроченная — это нарушение допуска."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        person_id = await _person(sessionmaker, "Просроченный", "Работник")
        today = date.today()
        await async_client.post(
            _CORE,
            json={
                "person_id": person_id,
                "name": "Аттестация ПБ",
                "area_code": "Б.2",
                "expires_at": str(today - timedelta(days=1)),
            },
            headers=headers,
        )
        listed = await async_client.get(f"{_API}/attestations", headers=headers)
        row = next(
            r for r in listed.json()["items"] if r["person_name"] == "Просроченный Работник"
        )
        assert row["validity_status"] == "overdue"
        assert row["validity_status_label"] == "Просрочена"


class TestСводкаАттестации:
    async def test_счётчики_аттестации_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        today = date.today()

        person_ok = await _person(sessionmaker, "Действующий", "Работник")
        person_bad = await _person(sessionmaker, "Истёкший", "Работник")
        await async_client.post(
            _CORE,
            json={
                "person_id": person_ok,
                "name": "Аттестация ПБ",
                "area_code": "Б.3",
                "expires_at": str(today + timedelta(days=900)),
            },
            headers=headers,
        )
        await async_client.post(
            _CORE,
            json={
                "person_id": person_bad,
                "name": "Аттестация ПБ",
                "area_code": "Б.4",
                "expires_at": str(today - timedelta(days=10)),
            },
            headers=headers,
        )

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["attestations_total"] == before["attestations_total"] + 2
        assert after["attestations_overdue"] == before["attestations_overdue"] + 1

    async def test_аттестации_без_области_в_сводку_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сводка ПромБеза считает СВОИ записи, а не все аттестации арендатора."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        person_id = await _person(sessionmaker, "Чужая", "Дисциплина")
        await async_client.post(
            _CORE,
            json={"person_id": person_id, "name": "Аттестация по электробезопасности"},
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["attestations_total"] == before["attestations_total"]


class TestСправочникОбластей:
    async def test_все_области_из_справочника_принимаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        from app.core.disciplines import ATTESTATION_AREA_TITLES

        headers = await make_auth_headers()
        person_id = await _person(sessionmaker, "Многостаночник", "Иван")
        for code in ATTESTATION_AREA_TITLES:
            response = await async_client.post(
                _CORE,
                json={
                    "person_id": person_id,
                    "name": f"Аттестация {code}",
                    "area_code": code,
                },
                headers=headers,
            )
            assert response.status_code == 201, f"{code}: {response.text}"

    async def test_каждая_область_размечена_промбезом(self) -> None:
        """Справочник обязан быть размечен дисциплиной, иначе он снова немой.

        Пустая разметка означала бы «область есть, а чья она — неизвестно», и
        сводка дисциплины не смогла бы отобрать свои записи.
        """

        from app.core.disciplines import (
            ATTESTATION_AREA_DISCIPLINE,
            ATTESTATION_AREA_TITLES,
            Discipline,
        )

        assert set(ATTESTATION_AREA_DISCIPLINE) == set(ATTESTATION_AREA_TITLES)
        assert all(
            discipline is Discipline.INDUSTRIAL_SAFETY
            for discipline in ATTESTATION_AREA_DISCIPLINE.values()
        )
