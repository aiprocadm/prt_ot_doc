"""Подсказки мастера для отчётности ГО и ЧС — из реестров контура (срез-43).

ЧТО ЗАКРЫВАЕТСЯ. Срез-6 (разд. 56.1) записал границу: «формирования и личный
состав в системе есть, но подставлять их в документ платформа не умеет».
Решение владельца #960 сняло её для БДД, экологии и ПромБеза — подсказкой с
источником, а не ответом. ГО и ЧС оставалась единственной отчётностью, где
специалист переписывал в отчёт числа, которые сводка готовности показывает
на соседнем экране. После этого среза подсказки есть у ВСЕХ комплектов
отчётности.

ЧТО ПРОВЕРЯЕТСЯ:

* формирования считаются по реестру, виды названы в источнике;
* личный состав — ТЕМ ЖЕ правилом, что сводка готовности: строки без даты
  вывода. Выведенный боец в подсказку не попадает;
* категория объекта — правило ЕДИНСТВЕННОГО объекта (как у НВОС): один
  профиль подсказывается, несколько — нет, ни одного — нет;
* граница: СИЗ, оповещение, всё о ЧС, период и составитель НЕ подсказываются;
* у каждой подсказки есть источник.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import Company, Person, Site, Tenant
from app.modules.packs.definitions import PACK_CODE_GOCHS_REPORTS

pytestmark = pytest.mark.anyio

_API = "/api/v1/civil-defense"
_FIELDS = "/api/v1/packs/scenarios"


async def _grant(sessionmaker, code: str = "civil_defense") -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=True))
        else:
            grant.on = True
        await session.commit()


async def _company(session) -> Company:
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
    company = (
        (await session.execute(select(Company).where(Company.tenant_id == tenant.id)))
        .scalars()
        .first()
    )
    if company is None:
        company = Company(tenant_id=tenant.id, name="Головная компания")
        session.add(company)
        await session.flush()
    return company


async def _person(sessionmaker, last_name: str) -> str:
    async with sessionmaker() as session:
        company = await _company(session)
        person = Person(
            tenant_id=company.tenant_id,
            company_id=company.id,
            last_name=last_name,
            first_name="Пётр",
            middle_name="Иванович",
        )
        session.add(person)
        await session.commit()
        return str(person.id)


async def _site(sessionmaker, name: str) -> str:
    async with sessionmaker() as session:
        company = await _company(session)
        site = Site(tenant_id=company.tenant_id, company_id=company.id, name=name)
        session.add(site)
        await session.commit()
        return str(site.id)


async def _formation(async_client, headers, name: str, kind: str = "nasf") -> dict:
    response = await async_client.post(
        f"{_API}/formations", json={"name": name, "kind": kind}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _member(async_client, headers, formation_id: str, person_id: str) -> dict:
    response = await async_client.post(
        f"{_API}/formations/{formation_id}/members",
        json={"person_id": person_id, "role_in_formation": "Боец"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _profile(
    async_client, headers, site_id: str, *, category: str, responsible: str | None = None
) -> dict:
    payload: dict[str, object] = {"site_id": site_id, "category": category}
    if responsible is not None:
        payload["responsible"] = responsible
    response = await async_client.post(f"{_API}/profiles", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _fields(async_client, headers) -> dict:
    response = await async_client.get(
        f"{_FIELDS}/{PACK_CODE_GOCHS_REPORTS}/fields", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return {f["name"]: f for f in body["fields"]} | {"__body__": body}


class TestФормирования:
    async def test_формирования_считаются_по_реестру_с_видами_в_источнике(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _formation(async_client, headers, "Звено пожаротушения", "nasf")
        await _formation(async_client, headers, "Пост РХН", "nasf")
        await _formation(async_client, headers, "Звено связи", "nfgo")

        fields = await _fields(async_client, headers)
        field = fields["gochs_formations_count"]
        assert field["suggested"] == "3"
        assert "НАСФ — 2" in field["suggested_source"]
        assert "НФГО — 1" in field["suggested_source"]
        # Подсказка — не ответ: вопрос как был необязательным, так и остался.
        assert field["required"] is False

    async def test_пустой_реестр_подсказывает_честный_ноль(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ноль здесь — ответ реестра, а не молчание специалиста."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        fields = await _fields(async_client, headers)
        assert fields["gochs_formations_count"]["suggested"] == "0"
        assert fields["gochs_personnel_count"]["suggested"] == "0"
        assert fields["__body__"]["suggestions_note"]


class TestЛичныйСостав:
    async def test_считаются_только_действующие_строки_состава(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Правило ТО ЖЕ, что у сводки готовности: выведенный не в счёте."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, "Звено связи")
        active = await _person(sessionmaker, "Связистов")
        released = await _person(sessionmaker, "Уволенный")
        await _member(async_client, headers, formation["id"], active)
        member = await _member(async_client, headers, formation["id"], released)
        out = await async_client.patch(
            f"{_API}/formations/{formation['id']}/members/{member['id']}",
            json={"released_on": str(date.today() - timedelta(days=3))},
            headers=headers,
        )
        assert out.status_code == 200, out.text

        fields = await _fields(async_client, headers)
        assert fields["gochs_personnel_count"]["suggested"] == "1"
        assert "выведенные не считаются" in fields["gochs_personnel_count"]["suggested_source"]

    async def test_число_совпадает_со_сводкой_готовности(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Два экрана — одно число: иначе непонятно, какое из них правда."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _formation(async_client, headers, "Звено А")
        second = await _formation(async_client, headers, "Звено Б", "nfgo")
        one = await _person(sessionmaker, "Первый")
        two = await _person(sessionmaker, "Второй")
        await _member(async_client, headers, first["id"], one)
        await _member(async_client, headers, second["id"], two)
        # Один человек в двух формированиях — две строки, и сводка считает так же.
        await _member(async_client, headers, second["id"], one)

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        summary = readiness.json()
        fields = await _fields(async_client, headers)
        assert fields["gochs_personnel_count"]["suggested"] == str(summary["members_active"])
        assert fields["gochs_formations_count"]["suggested"] == str(summary["total_formations"])


class TestКатегорияОбъекта:
    async def test_единственный_объект_подсказывает_категорию_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site = await _site(sessionmaker, "Единственная площадка")
        await _profile(
            async_client, headers, site, category="first", responsible="Гражданский И.И."
        )

        fields = await _fields(async_client, headers)
        assert fields["facility_category"]["suggested"] == "Первая категория по ГО"
        assert "единственного объекта" in fields["facility_category"]["suggested_source"]
        assert fields["gochs_responsible"]["suggested"] == "Гражданский И.И."

    async def test_несколько_объектов_категорию_не_подсказывают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """О котором из объектов положение — решает специалист, не платформа."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _site(sessionmaker, "Площадка 1")
        second = await _site(sessionmaker, "Площадка 2")
        await _profile(async_client, headers, first, category="first")
        await _profile(async_client, headers, second, category="second")

        fields = await _fields(async_client, headers)
        assert fields["facility_category"]["suggested"] is None
        assert fields["gochs_responsible"]["suggested"] is None
        # А счётные подсказки при этом никуда не делись.
        assert fields["gochs_formations_count"]["suggested"] == "0"

    async def test_без_ответственного_у_объекта_подсказки_ответственного_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пустой ответственный — «не назначен», подсказывать пустоту нечего."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site = await _site(sessionmaker, "Площадка без ответственного")
        await _profile(async_client, headers, site, category="none")

        fields = await _fields(async_client, headers)
        assert fields["facility_category"]["suggested"] == "Категория не присвоена"
        assert fields["gochs_responsible"]["suggested"] is None


class TestГраница:
    async def test_что_реестры_не_знают_не_подсказывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """СИЗ, оповещение, ЧС, период и составитель — не из реестров."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _formation(async_client, headers, "Звено")
        fields = await _fields(async_client, headers)
        for name in (
            "gochs_ppe_coverage",
            "gochs_alert_means",
            "gochs_event_at",
            "gochs_event_kind",
            "gochs_event_injured",
            "gochs_event_measures",
            "gochs_event_forces",
            "gochs_report_period",
            "gochs_report_author",
        ):
            assert fields[name]["suggested"] is None, name

    async def test_у_каждой_подсказки_есть_источник(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        site = await _site(sessionmaker, "Площадка")
        await _profile(async_client, headers, site, category="second")
        await _formation(async_client, headers, "Звено")
        fields = await _fields(async_client, headers)
        fields.pop("__body__")
        suggested = [f for f in fields.values() if f["suggested"] is not None]
        assert len(suggested) == 3
        assert all(f["suggested_source"] for f in suggested)
