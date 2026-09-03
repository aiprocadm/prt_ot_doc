"""Контур БДД срез-3 (Доп. №1 разд. 56.2): путевые листы и контроль выпуска.

Требование: «Медицинский и технический контроль: предрейсовые/послерейсовые
медосмотры, предрейсовый техконтроль, путевые листы, журналы». Этот срез
закрывает пункт целиком и попутно — «режим труда и отдыха» из пункта
«Водители»: время в рейсе считается из листа.

СВЕРКА нашла:

1. **Бумага печатается, а учёта за ней нет.** Комплект документов BDD_BASE уже
   выпускает «Порядок предрейсового медицинского осмотра» и «Порядок
   предрейсового контроля технического состояния» (``modules/packs``), но ни
   одного путевого листа и ни одной отметки осмотра в продукте не было. Тот же
   признак, что срез-2 нашёл у режима труда и отдыха: приказ оформлен,
   исполнение нигде не фиксируется.
2. **Предрейсовый осмотр — НЕ ядровой ``MedicalExam``.** Проверено до кода:
   виды ядрового медосмотра — ``periodic / preliminary / psychiatric /
   fluorography / health_book``, то есть профмедосмотры раз в год по вредным
   факторам. Предрейсовый — каждую смену и привязан к рейсу. Дубля нет; общее
   у них только слово «медосмотр».

Решения:

* **один лист вместо четырёх реестров**: машина, водитель и три отметки
  сходятся на одном документе, как в жизни. Отдельные списки осмотров
  пришлось бы сшивать по времени и фамилии;
* **журнал отдельной таблицей НЕ заводится**: журнал предрейсовых осмотров —
  это тот же реестр листов с отбором по датам, а не второе хранилище тех же
  фактов (прецедент словаря дисциплин: две копии разошлись бы);
* **отметка — ТРИ значения, а не флажок**: «не внесено» и «не пройден» —
  разные факты, и лечат их по-разному (прецедент пустого срока в срезе-1);
* **вердикт о выпуске СЧИТАЕТСЯ ПРИ ЧТЕНИИ** из двух обязательных отметок и
  полем не хранится (прецедент стажа в срезе-2: сохранённый вердикт разойдётся
  с отметками при первой правке);
* **послерейсовый осмотр в вердикт НЕ входит**: он обязателен перевозчикам
  пассажиров и опасных грузов, а вида перевозок платформа не знает (та же
  граница, что у тахографа в срезе-1);
* **сводка по листам считается ЗА ОКНО** в 30 дней и SQL-агрегатами: реестр
  растёт каждую смену, в отличие от парка и водительского состава;
* **лист выписывается только на живую машину и допущенного водителя** — это
  целостность, а не экспертиза.

ГРАНИЦА: платформа НЕ решает, законен ли выпуск и уложился ли водитель в
режим труда и отдыха. Обязательность послерейсового осмотра и норма времени
следуют из вида перевозок и суммирования за неделю — таких данных в системе
нет. Полей «законен ли выпуск», «превышено ли время» и «время за рулём» нет ни
в записи, ни в сводке: считается ВРЕМЯ В РЕЙСЕ, а сколько из него человек
реально вёл машину, платформа не знает.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
            personnel_number=f"ТН-{last_name}",
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


async def _pair(async_client, headers, sessionmaker, *, suffix: str = "") -> tuple:
    """Машина и допущенный водитель — минимум, без которого листа не бывает."""

    vehicle = await _vehicle(async_client, headers, plate=f"А123АА77{suffix or '7'}")
    person_id = await _person(sessionmaker, last_name=f"Шофёров{suffix}")
    driver = await _driver(
        async_client, headers, person_id, license_number=f"9900 12345{suffix or '6'}"
    )
    return vehicle, driver


async def _waybill(
    async_client,
    headers,
    vehicle: dict,
    driver: dict,
    *,
    number: str = "ПЛ-001",
    issued_on: date | None = None,
    departure_at: datetime | None = None,
    return_at: datetime | None = None,
    pre_trip_medical: str = "not_recorded",
    post_trip_medical: str = "not_recorded",
    pre_trip_technical: str = "not_recorded",
    status: str = "issued",
    expect: int = 201,
) -> dict:
    payload: dict[str, object] = {
        "number": number,
        "vehicle_id": vehicle["id"],
        "driver_id": driver["id"],
        "issued_on": str(issued_on or date.today()),
        "pre_trip_medical": pre_trip_medical,
        "post_trip_medical": post_trip_medical,
        "pre_trip_technical": pre_trip_technical,
        "status": status,
    }
    if departure_at is not None:
        payload["departure_at"] = departure_at.isoformat()
    if return_at is not None:
        payload["return_at"] = return_at.isoformat()
    response = await async_client.post(f"{_API}/waybills", json=payload, headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


class TestПутевойЛист:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/waybills", headers=headers)
        assert response.status_code == 404

    async def test_лист_берёт_машину_и_водителя_из_реестров(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Госномер и ФИО приходят из реестров, в листе они не хранятся."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        assert body["vehicle_plate"] == "А123АА777"
        assert body["vehicle_brand_model"] == "КамАЗ 5490"
        assert body["driver_name"] == "Шофёров Пётр Иванович"
        assert body["driver_license_number"] == "9900 123456"
        assert body["status_label"] == "Выдан"

    async def test_дубль_номера_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        await _waybill(async_client, headers, vehicle, driver, number="ПЛ-777")
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-777", expect=422
        )

    async def test_неизвестное_состояние_отметки_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            pre_trip_medical="ok",
            expect=422,
        )

    async def test_чужой_машины_и_водителя_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        response = await async_client.post(
            f"{_API}/waybills",
            json={
                "number": "ПЛ-404",
                "vehicle_id": "нет-такого",
                "driver_id": driver["id"],
                "issued_on": str(date.today()),
            },
            headers=headers,
        )
        assert response.status_code == 404


class TestОтметкиИВыпуск:
    """Три отметки, а не флажок: «не внесено» ≠ «не пройден»."""

    async def test_свежий_лист_не_подтверждён_а_не_нарушение(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Только что выписанный лист — «контроль не подтверждён», не «блок».

        Это разные вещи: осмотр ещё не проводили, а не провалили. Показать
        свежий лист нарушением значило бы каждое утро кричать о нарушениях,
        которых нет.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        assert body["release_status"] == "unconfirmed"
        assert body["release_status_label"] == "Контроль не подтверждён"
        assert body["pre_trip_medical_label"] == "Сведения не внесены"

    async def test_обе_обязательные_отметки_дают_подтверждённый_выпуск(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            pre_trip_medical="passed",
            pre_trip_technical="passed",
        )
        assert body["release_status"] == "confirmed"

    async def test_проваленный_осмотр_блокирует_выпуск(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            pre_trip_medical="failed",
            pre_trip_technical="passed",
        )
        assert body["release_status"] == "blocked"
        assert body["release_status_label"] == "Контроль не пройден"

    async def test_послерейсовый_осмотр_в_вердикт_не_входит(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: он обязателен не всем, а вида перевозок платформа не знает.

        Если бы послерейсовый входил в вердикт, у каждого перевозчика грузов
        выпуск оказывался бы неподтверждённым без всякого нарушения.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            pre_trip_medical="passed",
            pre_trip_technical="passed",
            post_trip_medical="not_recorded",
        )
        assert body["release_status"] == "confirmed"
        assert body["post_trip_medical"] == "not_recorded"

    async def test_вердикт_пересчитывается_после_правки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Вердикт считается, а не хранится: правка отметки меняет его сразу."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        assert body["release_status"] == "unconfirmed"
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"pre_trip_medical": "passed", "pre_trip_technical": "passed"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["release_status"] == "confirmed"

    async def test_вердикта_нет_среди_полей_записи(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: вердикт нельзя записать снаружи — его нет во входной схеме.

        Прими ручка ``release_status`` на вход — и появилось бы второе место
        правды, расходящееся с отметками.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"release_status": "confirmed"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["release_status"] == "unconfirmed"


class TestВремяВРейсе:
    """Режим труда и отдыха из пункта «Водители» — считается, а не хранится."""

    async def test_время_в_рейсе_считается_из_пары_дат(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        departure = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            issued_on=date(2026, 8, 30),
            departure_at=departure,
            return_at=departure + timedelta(hours=9, minutes=30),
        )
        assert body["trip_hours"] == 9.5

    async def test_без_дат_время_пустое_а_не_ноль(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Сведений нет» и «рейс длился нисколько» — разные утверждения."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        assert body["trip_hours"] is None

    async def test_возвращение_проставляется_вечером_отдельной_правкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Обычный день: утром выписали с выездом, вечером внесли возвращение.

        Проверка сравнивает НОВУЮ дату с уже лежащей в базе, и если та
        приходит из базы без часового пояса, а эта с ним — сравнение падает
        пятисоткой ровно на самом частом действии за смену.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        departure = datetime(2026, 8, 30, 8, 0, tzinfo=timezone.utc)
        body = await _waybill(
            async_client, headers, vehicle, driver, departure_at=departure
        )
        assert body["trip_hours"] is None
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"return_at": (departure + timedelta(hours=8)).isoformat()},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["trip_hours"] == 8.0

    async def test_возвращение_раньше_выезда_правкой_тоже_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        departure = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
        body = await _waybill(
            async_client, headers, vehicle, driver, departure_at=departure
        )
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"return_at": (departure - timedelta(hours=1)).isoformat()},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_возвращение_раньше_выезда_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        departure = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            departure_at=departure,
            return_at=departure - timedelta(hours=2),
            expect=422,
        )

    async def test_вердикта_о_превышении_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: норма следует из вида перевозок и недели, их в системе нет."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        departure = datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            departure_at=departure,
            return_at=departure + timedelta(hours=16),
        )
        assert body["trip_hours"] == 16.0
        assert not any(
            key in body for key in ("overtime", "rest_violation", "driving_hours")
        )


class TestЦелостностьРейса:
    async def test_на_списанное_тс_лист_не_выписывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(
            async_client, headers, plate="В001ВВ99", status="decommissioned"
        )
        person_id = await _person(sessionmaker, last_name="Списанов")
        driver = await _driver(
            async_client, headers, person_id, license_number="9900 000111"
        )
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-СПИС", expect=422
        )

    async def test_на_отстранённого_водителя_лист_не_выписывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ради этого допуск и заводился срезом-2."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers, plate="С002СС99")
        person_id = await _person(sessionmaker, last_name="Отстранёнов")
        driver = await _driver(
            async_client,
            headers,
            person_id,
            license_number="9900 000222",
            status="suspended",
        )
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-ОТСТР", expect=422
        )

    async def test_машину_и_водителя_сменить_нельзя(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Другая машина — это другой рейс, а не правка старого листа.

        Переписать лист на другую машину значило бы приписать чужому рейсу
        чужие отметки медосмотра.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        other = await _vehicle(async_client, headers, plate="Е003ЕЕ99")
        body = await _waybill(async_client, headers, vehicle, driver)
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"vehicle_id": other["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["vehicle_id"] == vehicle["id"]
        assert response.json()["vehicle_plate"] == "А123АА777"

    async def test_аннулирование_меняет_состояние_а_не_удаляет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(async_client, headers, vehicle, driver)
        response = await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"status": "cancelled"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["status_label"] == "Аннулирован"
        listing = await async_client.get(f"{_API}/waybills", headers=headers)
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()["items"]] == [body["id"]]


class TestЖурналЗаПериод:
    """Реестр с отбором по датам И ЕСТЬ журнал: второго списка не заводим."""

    async def test_отбор_по_датам_и_машине(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        today = date.today()
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-СТАРЫЙ",
            issued_on=today - timedelta(days=60),
        )
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-СВЕЖИЙ", issued_on=today
        )
        response = await async_client.get(
            f"{_API}/waybills",
            params={
                "issued_from": str(today - timedelta(days=7)),
                "vehicle_id": vehicle["id"],
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert [row["number"] for row in response.json()["items"]] == ["ПЛ-СВЕЖИЙ"]

    async def test_журнал_читается_от_свежих(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        today = date.today()
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-01",
            issued_on=today - timedelta(days=3),
        )
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-02", issued_on=today
        )
        response = await async_client.get(f"{_API}/waybills", headers=headers)
        assert [row["number"] for row in response.json()["items"]] == ["ПЛ-02", "ПЛ-01"]

    async def test_отбор_по_вердикту_о_выпуске(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        await _waybill(async_client, headers, vehicle, driver, number="ПЛ-ПУСТО")
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-ПРОВАЛ",
            pre_trip_medical="failed",
        )
        response = await async_client.get(
            f"{_API}/waybills", params={"release_status": "blocked"}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert [row["number"] for row in response.json()["items"]] == ["ПЛ-ПРОВАЛ"]

    async def test_отбор_в_базе_и_вердикт_при_чтении_дают_одно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож против расхождения двух выражений одного правила.

        Вердикт одной записи считает Python, а отбор журнала и счётчики сводки
        — база: тянуть тысячи листов за смену в память ради подсчёта нельзя.
        Значит правило записано дважды, и без этой проверки два выражения
        молча разойдутся — отбор начнёт врать, а заметят это не скоро.

        Перебираем ВСЕ девять сочетаний двух обязательных отметок, а не
        удобные три: расходятся такие пары как раз на краях.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        marks = ("not_recorded", "passed", "failed")
        for i, medical in enumerate(marks):
            for j, technical in enumerate(marks):
                await _waybill(
                    async_client,
                    headers,
                    vehicle,
                    driver,
                    number=f"ПЛ-{i}{j}",
                    pre_trip_medical=medical,
                    pre_trip_technical=technical,
                )

        everything = await async_client.get(
            f"{_API}/waybills", params={"limit": 200}, headers=headers
        )
        assert everything.status_code == 200, everything.text
        rows = everything.json()["items"]
        assert len(rows) == 9

        for verdict in ("confirmed", "unconfirmed", "blocked"):
            # что говорит вердикт при чтении
            expected = sorted(
                row["number"] for row in rows if row["release_status"] == verdict
            )
            # что отобрала база
            response = await async_client.get(
                f"{_API}/waybills",
                params={"release_status": verdict, "limit": 200},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            body = response.json()
            actual = sorted(row["number"] for row in body["items"])
            assert actual == expected, verdict
            # и счётчик страницы тоже: он считается тем же отбором
            assert body["total"] == len(expected), verdict

        # заодно проверяем, что девять листов разложились по всем трём
        # вердиктам — иначе проверка выше сравнивала бы пустое с пустым
        assert sorted(
            {row["release_status"] for row in rows}
        ) == ["blocked", "confirmed", "unconfirmed"]

    async def test_неизвестный_вердикт_в_отборе_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.get(
            f"{_API}/waybills", params={"release_status": "ok"}, headers=headers
        )
        assert response.status_code == 422


class TestСводка:
    async def test_окно_сводки_отсекает_старые_листы(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Реестр листов растёт каждую смену: «всего за три года» — не вопрос."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        today = date.today()
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-ДАВНО",
            issued_on=today - timedelta(days=90),
        )
        await _waybill(
            async_client, headers, vehicle, driver, number="ПЛ-СЕЙЧАС", issued_on=today
        )
        response = await async_client.get(f"{_API}/readiness", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["waybill_window_days"] == 30
        assert body["waybills_total"] == 1
        assert body["waybills_by_status"] == {"issued": 1, "closed": 0, "cancelled": 0}

    async def test_непройденное_и_невнесённое_не_складываются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Нарушение и дыра в учёте считаются РАЗНЫМИ счётчиками, не дважды."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        await _waybill(async_client, headers, vehicle, driver, number="ПЛ-ПУСТО")
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-ПРОВАЛ",
            pre_trip_medical="failed",
            pre_trip_technical="not_recorded",
        )
        await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-ОК",
            pre_trip_medical="passed",
            pre_trip_technical="passed",
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["waybills_total"] == 3
        assert body["waybills_release_blocked"] == 1
        assert body["waybills_release_unconfirmed"] == 1

    async def test_аннулированный_лист_нарушением_не_считается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """По аннулированному листу как раз видно, что выезда не было."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle, driver = await _pair(async_client, headers, sessionmaker)
        body = await _waybill(
            async_client,
            headers,
            vehicle,
            driver,
            number="ПЛ-АННУЛ",
            pre_trip_medical="failed",
        )
        await async_client.patch(
            f"{_API}/waybills/{body['id']}",
            json={"status": "cancelled"},
            headers=headers,
        )
        summary = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert summary["waybills_release_blocked"] == 0
        assert summary["waybills_by_status"]["cancelled"] == 1

    async def test_вердикта_о_законности_выпуска_в_сводке_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА-сторож: платформа не решает, законен ли выпуск."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in ("release_legal", "compliant", "violations", "rest_violations")
        )
