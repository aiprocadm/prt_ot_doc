"""Контур БДД срез-6 (Доп. №1 разд. 56.2): проверки знаний ПДД.

Требование: «Инструктажи и стажировки водителей, проверки знаний ПДД/БДД,
приказы об ответственных». Инструктажи закрыл срез-5, здесь — ПРОВЕРКИ
ЗНАНИЙ. Остаются стажировки: их в ядре нет вовсе (только поле
``internship_days`` в шаблоне документа), это отдельная работа.

СВЕРКА нашла:

1. **Своего реестра заводить НЕ НАДО.** Ядровая ``Attestation`` хранит ровно
   то, что нужно: человек аттестован по такому-то предмету до такой-то даты, с
   областью из ЗАКРЫТОГО справочника. Свой реестр «проверок знаний водителей»
   продублировал бы её целиком.
2. **Разметка областей дисциплиной УЖЕ БЫЛА НАПИСАНА — и ею никто не
   пользовался.** ``ATTESTATION_AREA_DISCIPLINE`` и
   ``discipline_of_attestation_area`` завела волна 54.2, но ни один контур их
   не читал: все области были промбезовскими, и разметка была тождественной.
   Этот срез — первый её потребитель.
3. **ЛОВУШКА, И ОНА СЕРЬЁЗНЕЕ САМОГО СРЕЗА.** Контур промбезопасности отбирал
   аттестации правилом ``area_code IS NOT NULL`` — «область заполнена, значит
   наша», причём в ДВУХ местах: список аттестаций и счётчики сводки. Правило
   было верным ровно до появления ВТОРОЙ дисциплины в справочнике. Заведи я
   область «ПДД» и не тронь отбор — проверка знаний водителя показалась бы на
   экране опасных производственных объектов как аттестация по
   промбезопасности, а просроченная попала бы в счётчик, по которому готовятся
   к проверке Ростехнадзора.

   Это тот же класс, что протухшая причина для ГО и ЧС (срез-1 контура БДД) и
   три копии словаря инструктажей (срез-5): условие, верное на момент
   написания, ломается от одного расширения, и заметить это некому.

Решения:

* **свой реестр НЕ заводится** — только область в общем справочнике;
* **код области не мимикрирует под Ростехнадзор**: «А.1» и «Б.9» — официальные
  шифры, у проверки знаний ПДД такой системы нет вовсе, и придумывать похожий
  код значило бы выдать самоделку за официальный;
* **разметка перестала быть сплошной**, а отбор во всех контурах идёт ПО
  ДИСЦИПЛИНЕ через один общий ``areas_of_discipline`` — два самодельных
  перебора разошлись бы, а третья дисциплина молча испортила бы отбор первым
  двум;
* **сводка БДД считает проверки, но реестром не владеет**: записи заводятся
  ядровыми ручками.

ГРАНИЦА: платформа НЕ решает, кому проверка знаний нужна и как часто — это
следует из вида перевозок и локальных приказов. Просрочка считается по
ВНЕСЁННОМУ сроку, а не по норме.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.disciplines import (
    ATTESTATION_AREA_DISCIPLINE,
    ATTESTATION_AREA_TITLES,
    Discipline,
    areas_of_discipline,
    discipline_of_attestation_area,
)
from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, Person
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/road-safety"
_OPO = "/api/v1/industrial-safety"
_CORE = "/api/v1/attestations"


async def _grant(sessionmaker, code: str, on: bool = True) -> None:
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
            session.add(
                FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on)
            )
        else:
            grant.on = on
        await session.commit()


async def _person(sessionmaker, last_name: str = "Водителев") -> str:
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
            first_name="Пётр",
            position_title="Водитель",
        )
        session.add(person)
        await session.commit()
        return person.id


async def _attestation(
    async_client,
    headers,
    person_id: str,
    *,
    area_code: str,
    expires_at: date | None,
    name: str = "Проверка знаний",
) -> dict:
    """Запись заводится ЯДРОВОЙ ручкой: своего реестра у БДД нет."""

    payload: dict[str, object] = {
        "person_id": person_id,
        "name": name,
        "area_code": area_code,
    }
    if expires_at is not None:
        payload["expires_at"] = str(expires_at)
    response = await async_client.post(_CORE, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestОбластьПДД:
    def test_область_заведена_и_размечена_бдд(self) -> None:
        assert "ПДД" in ATTESTATION_AREA_TITLES
        assert ATTESTATION_AREA_DISCIPLINE["ПДД"] is Discipline.ROAD_SAFETY
        assert discipline_of_attestation_area("ПДД") is Discipline.ROAD_SAFETY

    def test_разметка_перестала_быть_сплошной(self) -> None:
        """Раньше все области были промбезовскими — теперь дисциплин две.

        Именно из-за этого сломалось правило «область заполнена — значит
        промбез», на котором держался отбор в двух местах.
        """

        assert set(ATTESTATION_AREA_DISCIPLINE.values()) == {
            Discipline.INDUSTRIAL_SAFETY,
            Discipline.ROAD_SAFETY,
        }

    def test_каждая_область_размечена_и_подписана(self) -> None:
        """Неразмеченная область не попадёт ни в один контур — потеряется."""

        assert set(ATTESTATION_AREA_DISCIPLINE) == set(ATTESTATION_AREA_TITLES)
        for code, title in ATTESTATION_AREA_TITLES.items():
            assert title.strip(), code

    def test_отбор_по_дисциплине_делит_справочник_без_остатка(self) -> None:
        промбез = set(areas_of_discipline(Discipline.INDUSTRIAL_SAFETY))
        бдд = set(areas_of_discipline(Discipline.ROAD_SAFETY))
        assert промбез & бдд == set()
        assert промбез | бдд == set(ATTESTATION_AREA_TITLES)

    def test_чужие_области_не_переразмечены(self) -> None:
        """Сторож: срез добавляет своё, а не переписывает чужое."""

        assert discipline_of_attestation_area("Б.9") is Discipline.INDUSTRIAL_SAFETY
        assert discipline_of_attestation_area("А.1") is Discipline.INDUSTRIAL_SAFETY

    def test_код_области_не_мимикрирует_под_ростехнадзор(self) -> None:
        """«А.1» и «Б.9» — официальные шифры; у проверки знаний ПДД их нет.

        Придумать похожий код значило бы выдать самоделку за официальный шифр
        и навсегда запутать того, кто готовится к проверке.
        """

        for code in areas_of_discipline(Discipline.ROAD_SAFETY):
            assert not code.startswith(("А.", "Б."))


class TestЛовушкаЧужогоКонтура:
    """Главная проверка среза: ПДД не должна протечь в промбезопасность."""

    async def test_проверка_пдд_не_попадает_в_список_аттестаций_опо(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Отбор «область заполнена — значит наша» протух от одной строки.

        Без починки водительская проверка знаний показалась бы на экране
        опасных производственных объектов как аттестация по промбезопасности.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker, "industrial_safety")
        await _grant(sessionmaker, "road_safety")
        today = date.today()
        driver = await _person(sessionmaker, last_name="Шофёров")
        engineer = await _person(sessionmaker, last_name="Инженеров")
        await _attestation(
            async_client,
            headers,
            driver,
            area_code="ПДД",
            expires_at=today + timedelta(days=100),
        )
        await _attestation(
            async_client,
            headers,
            engineer,
            area_code="Б.9",
            expires_at=today + timedelta(days=100),
            name="Аттестация по промбезопасности",
        )

        response = await async_client.get(f"{_OPO}/attestations", headers=headers)
        assert response.status_code == 200, response.text
        areas = [row["area_code"] for row in response.json()["items"]]
        assert areas == ["Б.9"], areas

    async def test_просроченная_пдд_не_попадает_в_счётчики_опо(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Второе такое же место: счётчик просроченных аттестаций в сводке.

        Это число смотрят перед проверкой Ростехнадзора — просроченная
        водительская проверка знаний в нём была бы прямой ложью.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker, "industrial_safety")
        await _grant(sessionmaker, "road_safety")
        today = date.today()
        driver = await _person(sessionmaker, last_name="Шофёров")
        await _attestation(
            async_client,
            headers,
            driver,
            area_code="ПДД",
            expires_at=today - timedelta(days=30),
        )
        response = await async_client.get(f"{_OPO}/readiness", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["attestations_overdue"] == 0

    async def test_промбез_свои_записи_по_прежнему_видит(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож против перелечивания: починка не должна спрятать своё."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "industrial_safety")
        today = date.today()
        engineer = await _person(sessionmaker, last_name="Инженеров")
        await _attestation(
            async_client,
            headers,
            engineer,
            area_code="Б.8",
            expires_at=today - timedelta(days=5),
            name="Аттестация по промбезопасности",
        )
        listing = await async_client.get(f"{_OPO}/attestations", headers=headers)
        assert [r["area_code"] for r in listing.json()["items"]] == ["Б.8"]
        readiness = await async_client.get(f"{_OPO}/readiness", headers=headers)
        assert readiness.json()["attestations_overdue"] == 1


class TestСводкаБДД:
    async def test_проверки_знаний_считаются_в_сводке_бдд(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        today = date.today()
        first = await _person(sessionmaker, last_name="Первов")
        second = await _person(sessionmaker, last_name="Второв")
        await _attestation(
            async_client,
            headers,
            first,
            area_code="ПДД",
            expires_at=today + timedelta(days=200),
        )
        await _attestation(
            async_client,
            headers,
            second,
            area_code="ПДД",
            expires_at=today - timedelta(days=10),
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["knowledge_checks_total"] == 2
        assert body["knowledge_checks_overdue"] == 1

    async def test_чужие_аттестации_в_сводку_бдд_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Зеркало ловушки: контур БДД тоже обязан отбирать своё."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        today = date.today()
        engineer = await _person(sessionmaker, last_name="Инженеров")
        await _attestation(
            async_client,
            headers,
            engineer,
            area_code="Б.9",
            expires_at=today - timedelta(days=10),
            name="Аттестация по промбезопасности",
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["knowledge_checks_total"] == 0
        assert body["knowledge_checks_overdue"] == 0

    async def test_без_внесённого_срока_просрочки_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Срок не внесён» и «просрочено» — разные вещи (канон срезов 1–3)."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        person_id = await _person(sessionmaker, last_name="Бессрочев")
        await _attestation(
            async_client, headers, person_id, area_code="ПДД", expires_at=None
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["knowledge_checks_total"] == 1
        assert body["knowledge_checks_overdue"] == 0

    async def test_вердикта_о_необходимости_проверки_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: кому проверка нужна и как часто — не решение платформы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in (
                "knowledge_checks_required",
                "knowledge_checks_missing",
                "checks_schedule_compliant",
            )
        )
