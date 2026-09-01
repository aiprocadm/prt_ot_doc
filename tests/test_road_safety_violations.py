"""Контур БДД срез-8 (Доп. №1 разд. 56.2): учёт нарушений ПДД.

Требование: «Водители: водительский состав, стаж/категории, режим труда и
отдыха, НАРУШЕНИЯ». Состав, стаж и категории дал срез-2, режим труда и отдыха —
срез-3 (время в рейсе из путевого листа). Здесь закрывается последнее, и
**пункт «Водители» закрыт целиком**.

СВЕРКА нашла:

1. **Ядровое ``Violation`` НЕ ГОДИТСЯ.** Оно есть, и по имени казалось бы
   подходит — но у него ``inspection_id`` NOT NULL и ``clause_ref``: это
   находка ПРОВЕРКИ по пункту чек-листа. У нарушения ПДД никакой проверки нет:
   оно приходит постановлением ГИБДД или снимается камерой. Общее у них только
   слово. Второй раз за контур одно слово означало разные вещи (первый —
   «медосмотр» в срезе-3).
2. **Учёта нарушений не было никакого.**

Решения:

* **водитель НЕОБЯЗАТЕЛЕН, и это главное в модели**: камера фиксирует
  ГОСНОМЕР, а не человека. Постановление приходит собственнику, и кто был за
  рулём, организация выясняет сама — иногда никогда. NOT NULL заставлял бы
  вписывать наугад, а нарушения без установленного водителя — как раз то, что
  стоит показывать: организация платит, а разбираться не с кем;
* **машина ОБЯЗАТЕЛЬНА**: нарушение без своего ТС организации не касается;
* **способ выявления — ЗАКРЫТЫЙ словарь**, и деление не косметическое: от него
  зависит, известен ли водитель;
* **статья КоАП — СВОБОДНАЯ строка**: статей с частями многие десятки, они
  меняются поправками, и словарь в коде отстанет (довод марки и модели ТС);
* **«штраф не наложен» ≠ «штраф не оплачен»**: за первое платить нечего,
  второе это долг. Склеить их значило бы записать в долги каждое замечание
  собственного контроля;
* **состояние штрафа СЧИТАЕТСЯ** из суммы и даты оплаты, полем не хранится;
* **списанное ТС и отстранённый водитель разрешены** — как у ДТП: постановление
  приходит месяцами позже.

ГРАНИЦА: платформа НЕ устанавливает виновность, НЕ считает сроки обжалования и
скидку за раннюю оплату. Она хранит внесённое по постановлению и показывает,
что не оплачено.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, Person
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/road-safety"


async def _grant(sessionmaker, code: str = "road_safety", on: bool = True) -> None:
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


async def _person(sessionmaker, last_name: str = "Шофёров") -> str:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = (
            (
                await session.execute(
                    select(Company).where(Company.tenant_id == tenant.id)
                )
            )
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
            middle_name="Иванович",
            position_title="Водитель",
        )
        session.add(person)
        await session.commit()
        return str(person.id)


async def _vehicle(
    async_client, headers, *, plate: str = "А123АА777", status: str = "in_service"
) -> dict:
    response = await async_client.post(
        f"{_API}/vehicles",
        json={
            "plate_number": plate,
            "brand_model": "КамАЗ 5490",
            "kind": "truck",
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _driver(
    async_client,
    headers,
    person_id: str,
    *,
    license_number: str = "9900 123456",
    status: str = "admitted",
) -> dict:
    response = await async_client.post(
        f"{_API}/drivers",
        json={
            "person_id": person_id,
            "license_number": license_number,
            "categories": ["B", "C"],
            "status": status,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _violation(
    async_client,
    headers,
    vehicle: dict,
    *,
    driver: dict | None = None,
    occurred_at: datetime | None = None,
    source: str = "camera",
    article: str | None = "12.9 ч.2 КоАП",
    fine: str | None = None,
    paid_on: str | None = None,
    expect: int = 201,
) -> dict:
    payload: dict[str, object] = {
        "vehicle_id": vehicle["id"],
        "occurred_at": (
            occurred_at or datetime.now(timezone.utc) - timedelta(days=3)
        ).isoformat(),
        "source": source,
    }
    if driver is not None:
        payload["driver_id"] = driver["id"]
    if article is not None:
        payload["article"] = article
    if fine is not None:
        payload["fine_amount"] = fine
    if paid_on is not None:
        payload["fine_paid_on"] = paid_on
    response = await async_client.post(
        f"{_API}/violations", json=payload, headers=headers
    )
    assert response.status_code == expect, response.text
    return response.json()


class TestРегистрация:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/violations", headers=headers)
        assert response.status_code == 404

    async def test_нарушение_берёт_машину_из_реестра(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(async_client, headers, vehicle)
        assert body["vehicle_plate"] == "А123АА777"
        assert body["source_label"] == "Автоматическая фиксация (камера)"
        assert body["article"] == "12.9 ч.2 КоАП"

    async def test_неизвестный_способ_выявления_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _violation(async_client, headers, vehicle, source="радар", expect=422)

    async def test_нарушение_в_будущем_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _violation(
            async_client,
            headers,
            vehicle,
            occurred_at=datetime.now(timezone.utc) + timedelta(days=1),
            expect=422,
        )

    async def test_чужой_машины_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/violations",
            json={
                "vehicle_id": "нет-такой",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
            headers=headers,
        )
        assert response.status_code == 404

    async def test_на_списанное_тс_нарушение_регистрируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Постановление приходит месяцами позже — машину могли списать."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(
            async_client, headers, plate="В001ВВ99", status="decommissioned"
        )
        body = await _violation(async_client, headers, vehicle)
        assert body["vehicle_plate"] == "В001ВВ99"


class TestНеустановленныйВодитель:
    """Главное в модели: камера фиксирует машину, а не человека."""

    async def test_нарушение_без_водителя_законно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(async_client, headers, vehicle)
        assert body["driver_id"] is None
        assert body["driver_name"] is None
        # отдельный признак, чтобы экран не гадал по пустому имени
        assert body["driver_identified"] is False

    async def test_водителя_дописывают_правкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ради этого правка и нужна: водителя устанавливают позже."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        driver = await _driver(async_client, headers, await _person(sessionmaker))
        body = await _violation(async_client, headers, vehicle)
        assert body["driver_identified"] is False
        response = await async_client.patch(
            f"{_API}/violations/{body['id']}",
            json={"driver_id": driver["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["driver_identified"] is True
        assert response.json()["driver_name"] == "Шофёров Пётр Иванович"

    async def test_ошибочно_приписанного_водителя_можно_снять(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        driver = await _driver(async_client, headers, await _person(sessionmaker))
        body = await _violation(async_client, headers, vehicle, driver=driver)
        assert body["driver_identified"] is True
        response = await async_client.patch(
            f"{_API}/violations/{body['id']}",
            json={"driver_id": None},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["driver_identified"] is False

    async def test_на_отстранённого_водителя_нарушение_регистрируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Водителя могли отстранить ИЗ-ЗА этого нарушения."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="С002СС99")
        driver = await _driver(
            async_client,
            headers,
            await _person(sessionmaker, last_name="Отстранёнов"),
            license_number="9900 000222",
            status="suspended",
        )
        body = await _violation(async_client, headers, vehicle, driver=driver)
        assert body["driver_identified"] is True


class TestШтраф:
    async def test_без_суммы_штраф_не_наложен(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Не наложен» ≠ «не оплачен»: за первое платить нечего."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(
            async_client, headers, vehicle, source="internal", fine=None
        )
        assert body["fine_status"] == "none"
        assert body["fine_status_label"] == "Штраф не наложен"

    async def test_сумма_без_даты_оплаты_это_долг(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(async_client, headers, vehicle, fine="1500.00")
        assert body["fine_status"] == "unpaid"
        assert body["fine_status_label"] == "Не оплачен"

    async def test_состояние_пересчитывается_после_оплаты(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Состояние считается, а не хранится: проставили дату — изменилось."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(async_client, headers, vehicle, fine="1500.00")
        assert body["fine_status"] == "unpaid"
        response = await async_client.patch(
            f"{_API}/violations/{body['id']}",
            json={"fine_paid_on": "2026-08-20"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["fine_status"] == "paid"

    async def test_состояние_снаружи_не_записывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: прими ручка ``fine_status`` — появилось бы второе место
        правды, расходящееся с суммой и датой."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _violation(async_client, headers, vehicle, fine="1500.00")
        response = await async_client.patch(
            f"{_API}/violations/{body['id']}",
            json={"fine_status": "paid"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["fine_status"] == "unpaid"

    async def test_отрицательная_сумма_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _violation(async_client, headers, vehicle, fine="-100", expect=422)


class TestОтборИСогласиеПравил:
    async def test_отбор_в_базе_и_состояние_при_чтении_дают_одно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож против расхождения двух выражений одного правила.

        Состояние одной записи считает Python, а отбор и счётчики сводки —
        база: нарушений у большого парка тысячи. Значит правило записано
        дважды, и без этой проверки два выражения молча разойдутся.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _violation(async_client, headers, vehicle, fine=None)
        await _violation(async_client, headers, vehicle, fine="0")
        await _violation(async_client, headers, vehicle, fine="500.00")
        await _violation(
            async_client, headers, vehicle, fine="700.00", paid_on="2026-08-20"
        )

        everything = await async_client.get(
            f"{_API}/violations", params={"limit": 200}, headers=headers
        )
        rows = everything.json()["items"]
        assert len(rows) == 4
        for value in ("none", "unpaid", "paid"):
            expected = sorted(r["id"] for r in rows if r["fine_status"] == value)
            response = await async_client.get(
                f"{_API}/violations",
                params={"fine_status": value, "limit": 200},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert sorted(r["id"] for r in body["items"]) == expected, value
            assert body["total"] == len(expected), value
        assert sorted({r["fine_status"] for r in rows}) == ["none", "paid", "unpaid"]

    async def test_неизвестное_состояние_в_отборе_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.get(
            f"{_API}/violations", params={"fine_status": "долг"}, headers=headers
        )
        assert response.status_code == 422

    async def test_реестр_читается_от_свежих(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        now = datetime.now(timezone.utc)
        await _violation(
            async_client,
            headers,
            vehicle,
            article="старое",
            occurred_at=now - timedelta(days=30),
        )
        await _violation(
            async_client,
            headers,
            vehicle,
            article="свежее",
            occurred_at=now - timedelta(hours=1),
        )
        response = await async_client.get(f"{_API}/violations", headers=headers)
        assert [r["article"] for r in response.json()["items"]] == [
            "свежее",
            "старое",
        ]


class TestСводка:
    async def test_сводка_считает_долги_и_неустановленных(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        driver = await _driver(async_client, headers, await _person(sessionmaker))
        await _violation(async_client, headers, vehicle, fine="1500.00")
        await _violation(
            async_client, headers, vehicle, driver=driver, fine="500.00"
        )
        await _violation(
            async_client,
            headers,
            vehicle,
            driver=driver,
            fine="700.00",
            paid_on="2026-08-20",
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["violation_window_days"] == 365
        assert body["violations_total"] == 3
        # без водителя — только первое
        assert body["violations_without_driver"] == 1
        # оплаченное в долги не попадает
        assert body["fines_unpaid_count"] == 2
        assert body["fines_unpaid_amount"] == 2000.0

    async def test_окно_сводки_годовое(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        now = datetime.now(timezone.utc)
        await _violation(
            async_client, headers, vehicle, occurred_at=now - timedelta(days=400)
        )
        await _violation(
            async_client, headers, vehicle, occurred_at=now - timedelta(days=100)
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["violations_total"] == 1

    async def test_замечание_без_штрафа_в_долги_не_попадает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Иначе каждое замечание собственного контроля стало бы долгом."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _violation(async_client, headers, vehicle, source="internal", fine=None)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["violations_total"] == 1
        assert body["fines_unpaid_count"] == 0
        assert body["fines_unpaid_amount"] == 0.0

    async def test_вердикта_о_виновности_и_обжаловании_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: виновность и сроки обжалования — не дело платформы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in (
                "appeal_deadline",
                "discount_available",
                "driver_at_fault",
                "violations_compliant",
            )
        )
