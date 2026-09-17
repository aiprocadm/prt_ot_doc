"""Подсказки мастера фабрики из реестров (решение владельца, handoff #960).

ЗАЧЕМ ЭТО ПОНАДОБИЛОСЬ. Три комплекта отчётности подряд — экология (разд.
55.3), БДД (56.2 срез-9) и ГО-ЧС (56.1 срез-6) — заставили написать одну и ту
же границу: «числа в отчёт вносит специалист, платформа их из реестров не
собирает». При этом реестры полны: парк, водители, ДТП, нарушения. Человек
открывал отчёт и вручную переписывал в него то, что система уже знает.

ГЛАВНОЕ РЕШЕНИЕ, И ОНО НЕ ПРО УДОБСТВО: **подсказка, а не ответ.**

Значение из реестра приходит отдельным полем и НЕ становится ответом само
собой. Причина не в осторожности, а в том, чьё имя стоит под документом:
отчёт подписывает специалист, и он отвечает за каждое число в нём. Подставь
платформа число молча — человек подписал бы то, чего не проверял, а
расхождение реестра с действительностью стало бы ЕГО расхождением.

Второе решение: **подсказка всегда с ИСТОЧНИКОМ**. Число без объяснения,
откуда оно и за какой срок, проверить нельзя — а неподтверждаемую подсказку
предлагать бессмысленно.

Третье: **окно подсказок то же, что у сводки контура**. Два разных окна дали
бы два разных числа на соседних экранах, и специалист не смог бы понять,
какое из них правда.

ГРАНИЦА ОСТАЁТСЯ: платформа не решает, какой период у отчёта и какие числа в
нём верны. Она показывает своё и называет, откуда оно.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, Person
from app.models.models import Tenant
from app.modules.packs.context import enrich_context
from app.modules.packs.definitions import (
    PACK_CODE_BDD_REPORTS,
    PACK_CODE_CIVIL_DEFENCE,
)

pytestmark = pytest.mark.anyio

_ROAD = "/api/v1/road-safety"
_FIELDS = "/api/v1/packs/scenarios"


async def _grant(sessionmaker, code: str = "road_safety") -> None:
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


async def _person(sessionmaker, last_name: str = "Шофёров") -> str:
    async with sessionmaker() as session:
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
        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            last_name=last_name,
            first_name="Пётр",
            position_title="Водитель",
        )
        session.add(person)
        await session.commit()
        return str(person.id)


async def _fields(async_client, headers, pack_code: str) -> dict:
    response = await async_client.get(f"{_FIELDS}/{pack_code}/fields", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {f["name"]: f for f in body["fields"]} | {"__body__": body}


async def _vehicle(async_client, headers, *, plate: str, status: str = "in_service"):
    response = await async_client.post(
        f"{_ROAD}/vehicles",
        json={
            "plate_number": plate,
            "brand_model": "КамАЗ",
            "kind": "truck",
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestПодсказкаНеОтвет:
    """Главное в срезе: подписывать отчёт будет человек, а не платформа."""

    async def test_подсказка_приходит_отдельным_полем(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")
        await _vehicle(async_client, headers, plate="В222ВВ77")

        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_vehicles"]["suggested"] == "2"
        # и это НЕ ответ: поле вопроса, а не значение документа
        assert fields["bdd_report_vehicles"]["required"] is False

    async def test_подсказка_не_попадает_в_документ_сама(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """САМОЕ ВАЖНОЕ.

        Мастер отдал подсказку — но пока специалист её не подтвердил, документ
        обязан говорить «сведения не внесены». Иначе человек подпишет число,
        которого не проверял.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")

        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_vehicles"]["suggested"] == "1"

        # ответов специалист НЕ давал
        context = enrich_context(
            PACK_CODE_BDD_REPORTS,
            {"company": {"name": "Тест"}},
            {"bdd_report_period": "2026", "bdd_report_author": "Иванов"},
        )
        assert context["data"]["bdd_report_vehicles"] == "сведения не внесены"

    async def test_подтверждённая_подсказка_доходит_до_документа(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Подтвердил — попало. Это и есть весь механизм."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        suggested = fields["bdd_report_vehicles"]["suggested"]

        context = enrich_context(
            PACK_CODE_BDD_REPORTS,
            {"company": {"name": "Тест"}},
            {
                "bdd_report_period": "2026",
                "bdd_report_author": "Иванов",
                "bdd_report_vehicles": suggested,
            },
        )
        assert context["data"]["bdd_report_vehicles"] == "1"


class TestИсточникОбязателен:
    async def test_у_каждой_подсказки_есть_источник(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Число без объяснения, откуда оно, проверить нельзя.

        А неподтверждаемую подсказку предлагать бессмысленно: специалист либо
        поверит не глядя, либо не поверит вовсе.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")

        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        for name, field in fields.items():
            if name == "__body__":
                continue
            if field["suggested"] is None:
                assert field["suggested_source"] is None, name
            else:
                assert field["suggested_source"], name
                assert field["suggested_source"].strip(), name

    async def test_источник_называет_срок_у_событий(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«ДТП: 3» без срока — бесполезное число: за месяц или за три года?"""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert "365" in fields["bdd_report_accidents"]["suggested_source"]
        assert "365" in fields["bdd_report_violations"]["suggested_source"]

    async def test_пояснение_словами_есть_на_экране(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Человек должен понимать, что число предложено, а не подтверждено."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")
        body = (await _fields(async_client, headers, PACK_CODE_BDD_REPORTS))["__body__"]
        assert body["suggestions_note"]
        assert "подпис" in body["suggestions_note"].lower()


class TestЧтоСчитается:
    async def test_списанные_и_отстранённые_в_подсказку_не_идут(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Отчёт спрашивает «в эксплуатации» и «допущено» — их и считаем."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА77")
        await _vehicle(async_client, headers, plate="В222ВВ77", status="decommissioned")
        person_id = await _person(sessionmaker)
        await async_client.post(
            f"{_ROAD}/drivers",
            json={
                "person_id": person_id,
                "license_number": "9900 111222",
                "categories": ["B"],
                "status": "suspended",
            },
            headers=headers,
        )
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_vehicles"]["suggested"] == "1"
        assert fields["bdd_report_drivers"]["suggested"] == "0"

    async def test_пострадавшие_и_погибшие_одной_подсказкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """В форме они одной строкой — разносить по двум подсказкам значило бы
        предлагать то, чего в документе нет."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="А111АА77")
        await async_client.post(
            f"{_ROAD}/accidents",
            json={
                "occurred_at": (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                "place": "трасса",
                "vehicle_id": vehicle["id"],
                "kind": "collision",
                "injured_count": 2,
                "fatalities_count": 1,
            },
            headers=headers,
        )
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_accidents"]["suggested"] == "1"
        assert fields["bdd_report_injured"]["suggested"] == "2 / 1"

    async def test_пустой_реестр_даёт_ноль_а_не_молчание(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Здесь ноль ЧЕСТЕН: реестр пуст, и это проверяемый факт.

        Отличие от умолчаний документа, где «не внесено» ≠ «ноль»: там
        молчание специалиста, здесь ответ реестра.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_accidents"]["suggested"] == "0"
        assert fields["bdd_report_accidents"]["suggested_source"]


class TestГраница:
    async def test_комплект_без_источника_подсказок_не_получает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пусто — законный ответ, а не «не нашли».

        Базовый комплект ГО и ЧС (приказ, план, комиссия) состоит из решений
        специалиста — кто отвечает, в каком порядке оповещают; реестры на такие
        вопросы не отвечают, и выдумывать подсказку значило бы предложить
        ответ, ни на чём не основанный. (Отчётность ГО и ЧС с среза-43
        подсказки ПОЛУЧАЕТ — см. test_packs_prefill_civil_defense.py.)
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker, "civil_defense")
        fields = await _fields(async_client, headers, PACK_CODE_CIVIL_DEFENCE)
        body = fields.pop("__body__")
        assert all(f["suggested"] is None for f in fields.values())
        assert body["suggestions_note"] is None

    async def test_период_отчёта_не_подсказывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: какой период у отчёта, решает специалист.

        Подскажи платформа «2026 год» — и она решила бы за него, о чём отчёт.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        fields = await _fields(async_client, headers, PACK_CODE_BDD_REPORTS)
        assert fields["bdd_report_period"]["suggested"] is None
        assert fields["bdd_report_author"]["suggested"] is None
