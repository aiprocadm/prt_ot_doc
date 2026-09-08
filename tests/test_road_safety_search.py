"""Текстовый отбор по реестрам БДД ищет В БАЗЕ (Доп. №1 разд. 56.2, срез-123).

ЗАЧЕМ. Экран БДД грузил по 200 строк каждого реестра и искал в памяти. Пока
парк маленький, разницы нет; у арендатора с большим парком поиск по номеру
машины молча не находил существующую машину — она просто не попала на
страницу. «Ничего не найдено» вместо «вот ваша машина» — худший ответ реестра:
человек верит ему и заводит дубль.

ЧТО ПРОВЕРЯЕТСЯ: находится запись ЗА пределами первой страницы; ищется теми
словами, что видит человек (вид ТС — по подписи, а не по коду); пустой запрос
не режет реестр.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.tenanting import Tenant

_API = "/api/v1/road-safety"


async def _grant(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == "road_safety"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="road_safety", title="БДД")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=True))
        await session.commit()


async def _vehicle(async_client, headers, *, plate: str, kind: str = "truck", **extra) -> dict:
    payload = {
        "plate_number": plate,
        "brand_model": extra.pop("brand_model", "КамАЗ 5490"),
        "kind": kind,
        "status": extra.pop("status", "in_service"),
        "tachograph_installed": False,
        **extra,
    }
    response = await async_client.post(f"{_API}/vehicles", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestОтборТранспорта:
    async def test_машина_находится_за_пределами_страницы(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Главное свойство: искомое не обязано быть на загруженной странице."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for i in range(12):
            await _vehicle(async_client, headers, plate=f"А{100 + i}АА777")
        await _vehicle(async_client, headers, plate="Х999ХХ99", brand_model="ГАЗель Next")

        # страница из трёх строк искомое не содержит
        page = await async_client.get(
            f"{_API}/vehicles", params={"limit": 3, "offset": 0}, headers=headers
        )
        assert page.status_code == 200
        assert all(item["plate_number"] != "Х999ХХ99" for item in page.json()["items"])

        found = await async_client.get(
            f"{_API}/vehicles", params={"q": "Х999", "limit": 3}, headers=headers
        )
        assert found.status_code == 200, found.text
        assert [item["plate_number"] for item in found.json()["items"]] == ["Х999ХХ99"]
        assert found.json()["total"] == 1

    async def test_ищется_по_марке_и_регистр_не_мешает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА777", brand_model="ГАЗель Next")
        await _vehicle(async_client, headers, plate="Б222ББ777", brand_model="КамАЗ 5490")

        found = await async_client.get(f"{_API}/vehicles", params={"q": "газель"}, headers=headers)
        assert [i["plate_number"] for i in found.json()["items"]] == ["А111АА777"]

    async def test_вид_ищется_подписью_а_не_кодом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """В подсказке написано «поиск по виду» — человек пишет «автобус», не `bus`."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА777", kind="truck")
        await _vehicle(async_client, headers, plate="Б222ББ777", kind="bus")

        found = await async_client.get(f"{_API}/vehicles", params={"q": "автобус"}, headers=headers)
        assert [i["plate_number"] for i in found.json()["items"]] == ["Б222ББ777"]

    async def test_пустой_запрос_не_режет_реестр(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пустая строка поиска означает «условия нет», а не «ничего не подходит»."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА777")

        for value in ("", "   "):
            page = await async_client.get(f"{_API}/vehicles", params={"q": value}, headers=headers)
            assert page.json()["total"] == 1, value

    async def test_ничего_не_подходит_это_пустой_список(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА777")

        page = await async_client.get(
            f"{_API}/vehicles", params={"q": "такого нет"}, headers=headers
        )
        assert page.status_code == 200
        assert page.json()["items"] == []
        assert page.json()["total"] == 0


async def _driver(async_client, headers, data_factory, sessionmaker, *, last_name: str) -> dict:
    """Карточка водителя: имя живёт в кадровой записи, своей копии у неё нет."""

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        # Своя организация на каждого: у фабрики имя по умолчанию одно, и
        # второй вызов в том же тесте упёрся бы в уникальность названия.
        company = await data_factory.create_company(
            tenant=tenant, name=f"ООО {last_name}", session=session
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Иван",
            last_name=last_name,
            session=session,
        )
        await session.commit()
        person_id = str(person.id)

    response = await async_client.post(
        f"{_API}/drivers",
        json={
            "person_id": person_id,
            "license_number": f"77 АА {abs(hash(last_name)) % 900000 + 100000}",
            "categories": ["B", "C"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestОтборПутевых:
    async def test_путевой_находится_по_номеру_машины(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Номер листа человек помнит редко — ищет по машине, как обещает подсказка."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="Е777КХ99")
        other = await _vehicle(async_client, headers, plate="А111АА777")
        driver = await _driver(
            async_client, headers, data_factory, sessionmaker, last_name="Сидоров"
        )

        for vid, number in ((vehicle["id"], "ПЛ-001"), (other["id"], "ПЛ-002")):
            response = await async_client.post(
                f"{_API}/waybills",
                json={
                    "number": number,
                    "vehicle_id": vid,
                    "driver_id": driver["id"],
                    "issued_on": str(date.today() - timedelta(days=1)),
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        found = await async_client.get(f"{_API}/waybills", params={"q": "Е777"}, headers=headers)
        assert found.status_code == 200, found.text
        assert [i["number"] for i in found.json()["items"]] == ["ПЛ-001"]

    async def test_путевой_находится_по_фамилии_водителя(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Фамилия лежит в кадровой записи — без соединения поиск её не увидит."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="А111АА777")
        свой = await _driver(
            async_client, headers, data_factory, sessionmaker, last_name="Кузнецов"
        )
        чужой = await _driver(
            async_client, headers, data_factory, sessionmaker, last_name="Николаев"
        )

        for did, number in ((свой["id"], "ПЛ-010"), (чужой["id"], "ПЛ-011")):
            response = await async_client.post(
                f"{_API}/waybills",
                json={
                    "number": number,
                    "vehicle_id": vehicle["id"],
                    "driver_id": did,
                    "issued_on": str(date.today()),
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        found = await async_client.get(f"{_API}/waybills", params={"q": "кузнец"}, headers=headers)
        assert [i["number"] for i in found.json()["items"]] == ["ПЛ-010"]


class TestРегистрКириллицы:
    """Поиск обязан вести себя ОДИНАКОВО в разработке и в бою.

    Встроенные ``lower()`` и ``LIKE`` в SQLite знают только латиницу: «ГАЗель»
    и «газель» для них разные слова, а PostgreSQL их отождествляет. Такое
    расхождение ловится только на живом сервере, поэтому SQLite научен
    понижать регистр по Unicode (``db/session._teach_sqlite_unicode_lower``).
    Здесь это проверяется на живом поиске, а не на самой функции.
    """

    async def test_регистр_кириллицы_не_мешает_поиску(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _vehicle(async_client, headers, plate="А111АА777", brand_model="ГАЗель Next")

        for needle in ("газель", "ГАЗЕЛЬ", "ГаЗеЛь"):
            found = await async_client.get(
                f"{_API}/vehicles", params={"q": needle}, headers=headers
            )
            assert [i["plate_number"] for i in found.json()["items"]] == ["А111АА777"], needle
