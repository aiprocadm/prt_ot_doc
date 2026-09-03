"""Контур БДД срез-4 (Доп. №1 разд. 56.2): учёт ДТП.

Требование: «Профилактика и учёт ДТП: регистрация ДТП, анализ, мероприятия по
предупреждению аварийности (связь с инцидентами и CAPA)».

СВЕРКА нашла:

1. **ДТП в продукте нет вовсе.** Как и в прошлых срезах, бумага печатается, а
   учёта за ней нет: комплект БДД выпускает «План мероприятий по
   предупреждению ДТП» (``modules/packs``), но ни одной записи о происшествии
   в системе не заводится.
2. **Ядровой инцидент подходит НЕ ПОЛНОСТЬЮ — проверено по коду ДО работы.**
   ``incident.site_id`` NOT NULL, а ДТП происходит на дороге, где площадки
   арендатора нет; ``incidenttype`` — перечисление в базе, общее для всего
   продукта. И главное: помятый бампер это ДТП, но не происшествие по охране
   труда.
3. **CAPA переиспользуется БЕЗ единой правки ядра.** ``corrective_actions``
   адресуется парой ``source_type`` + ``source_id`` и принимает любую строку —
   своей таблицы мероприятий контур БДД не заводит.

Решения:

* **своя запись + СВЯЗЬ, а не поглощение**: ``incident_id`` необязателен —
  пострадал человек, расследование идёт в ядре; пострадавших нет, ссылка
  пустая, и это законное состояние;
* **тяжесть СЧИТАЕТСЯ из чисел людей**, а не хранится словом (прецедент стажа
  в срезе-2 и вердикта о выпуске в срезе-3);
* **своего статуса «разобрано» У ДТП НЕТ**: состояние следует из ядровых
  мероприятий и ссылки на расследование. Собственная галочка разошлась бы с
  мероприятиями в первый же день;
* **вину вносит арендатор по документам ГИБДД**, по умолчанию «не
  установлена»: устанавливают её ГИБДД и суд, а не платформа;
* **водитель НЕОБЯЗАТЕЛЕН**: в стоящую машину въезжают и без него;
* **списанное ТС и отстранённый водитель РАЗРЕШЕНЫ** — в отличие от путевого
  листа: ДТП регистрируют задним числом, машину могли списать после аварии, а
  водителя отстранить из-за неё;
* **окно сводки ГОДОВОЕ**, а не месячное как у листов: ДТП редки.

ГРАНИЦА: платформа НЕ устанавливает вину и НЕ оценивает, достаточны ли
мероприятия. Состояние разбора — факт о незакрытых мероприятиях, а не оценка
«разобрано хорошо». Полей «виновата ли организация» и «достаточны ли меры» нет
ни в записи, ни в сводке.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
)
from app.models.master_data import Company, Person, Site
from app.models.models import Tenant
from app.models.safety_ops import CorrectiveAction

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


async def _company(session, tenant) -> Company:
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


async def _person(sessionmaker, last_name: str = "Шофёров") -> str:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = await _company(session, tenant)
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


async def _incident(sessionmaker) -> str:
    """Ядровое расследование: контур БДД инцидентов НЕ заводит."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = await _company(session, tenant)
        site = (
            (await session.execute(select(Site).where(Site.tenant_id == tenant.id)))
            .scalars()
            .first()
        )
        if site is None:
            site = Site(tenant_id=tenant.id, company_id=company.id, name="Площадка")
            session.add(site)
            await session.flush()
        incident = Incident(
            tenant_id=tenant.id,
            company_id=company.id,
            site_id=site.id,
            title="Наезд с пострадавшим",
            incident_type=IncidentType.ACCIDENT,
            severity=IncidentSeverity.HIGH,
            status=IncidentStatus.INVESTIGATING,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(incident)
        await session.commit()
        return str(incident.id)


async def _capa(sessionmaker, accident_id: str, *, status: str = "open") -> str:
    """Мероприятие в ЯДРОВОМ CAPA: своей таблицы контур БДД не заводит."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        action = CorrectiveAction(
            tenant_id=tenant.id,
            source_type="road_accident",
            source_id=accident_id,
            title="Внеплановый инструктаж водителей",
            action_type="corrective",
            status=status,
        )
        session.add(action)
        await session.commit()
        return str(action.id)


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


async def _accident(
    async_client,
    headers,
    vehicle: dict,
    *,
    driver: dict | None = None,
    occurred_at: datetime | None = None,
    place: str = "45 км трассы М-4",
    kind: str = "collision",
    injured: int = 0,
    fatalities: int = 0,
    fault: str = "not_established",
    incident_id: str | None = None,
    expect: int = 201,
) -> dict:
    payload: dict[str, object] = {
        "occurred_at": (
            occurred_at or datetime.now(timezone.utc) - timedelta(days=1)
        ).isoformat(),
        "place": place,
        "vehicle_id": vehicle["id"],
        "kind": kind,
        "injured_count": injured,
        "fatalities_count": fatalities,
        "fault": fault,
    }
    if driver is not None:
        payload["driver_id"] = driver["id"]
    if incident_id is not None:
        payload["incident_id"] = incident_id
    response = await async_client.post(
        f"{_API}/accidents", json=payload, headers=headers
    )
    assert response.status_code == expect, response.text
    return response.json()


class TestРегистрацияДТП:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/accidents", headers=headers)
        assert response.status_code == 404

    async def test_запись_берёт_машину_и_водителя_из_реестров(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        driver = await _driver(async_client, headers, await _person(sessionmaker))
        body = await _accident(async_client, headers, vehicle, driver=driver)
        assert body["vehicle_plate"] == "А123АА777"
        assert body["driver_name"] == "Шофёров Пётр Иванович"
        assert body["kind_label"] == "Столкновение"
        # вина по умолчанию НЕ «наш водитель»: её устанавливают ГИБДД и суд
        assert body["fault"] == "not_established"
        assert body["fault_label"] == "Не установлена"

    async def test_место_свободной_строкой_а_не_площадкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ДТП происходит на дороге: «45 км трассы» площадкой не является."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        assert body["place"] == "45 км трассы М-4"
        assert "site_id" not in body

    async def test_дтп_без_водителя_законно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """В стоящую машину въезжают и без водителя за рулём."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(
            async_client, headers, vehicle, kind="parked_vehicle"
        )
        assert body["driver_id"] is None
        assert body["driver_name"] is None

    async def test_неизвестный_вид_и_вина_отвергаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _accident(async_client, headers, vehicle, kind="дтп", expect=422)
        await _accident(async_client, headers, vehicle, fault="виноват", expect=422)

    async def test_дтп_в_будущем_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _accident(
            async_client,
            headers,
            vehicle,
            occurred_at=datetime.now(timezone.utc) + timedelta(days=2),
            expect=422,
        )

    async def test_отрицательное_число_пострадавших_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _accident(async_client, headers, vehicle, injured=-1, expect=422)


class TestЗаднимЧислом:
    """Отличие от путевого листа, и оно сознательное."""

    async def test_на_списанное_тс_дтп_регистрируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Машину могли списать ПОСЛЕ аварии — часто именно из-за неё.

        Путевой лист на списанную машину выписать нельзя: его выписывают
        наперёд. ДТП же регистрируют задним числом, и запрет сделал бы
        невозможной запись самых тяжёлых случаев.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(
            async_client, headers, plate="В001ВВ99", status="decommissioned"
        )
        body = await _accident(async_client, headers, vehicle, kind="rollover")
        assert body["vehicle_plate"] == "В001ВВ99"

    async def test_на_отстранённого_водителя_дтп_регистрируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Водителя могли отстранить ИЗ-ЗА этого же ДТП."""

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
        body = await _accident(async_client, headers, vehicle, driver=driver)
        assert body["driver_id"] == driver["id"]


class TestПоследствия:
    async def test_без_пострадавших_только_ущерб(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        assert body["consequences"] == "damage_only"
        assert body["consequences_label"] == "Только материальный ущерб"

    async def test_тяжесть_пересчитывается_после_уточнения(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Тяжесть считается из чисел: уточнили число — изменилась и она.

        Храни её словом — уточнение числа оставило бы слово прежним, и какое
        из двух правда, было бы непонятно.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        assert body["consequences"] == "damage_only"
        response = await async_client.patch(
            f"{_API}/accidents/{body['id']}",
            json={"injured_count": 2},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["consequences"] == "injured"

    async def test_погибшие_перевешивают_пострадавших(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(
            async_client, headers, vehicle, injured=3, fatalities=1
        )
        assert body["consequences"] == "fatal"

    async def test_тяжесть_снаружи_не_записывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: прими ручка ``consequences`` — появилось бы второе место
        правды, расходящееся с числами."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        response = await async_client.patch(
            f"{_API}/accidents/{body['id']}",
            json={"consequences": "fatal"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["consequences"] == "damage_only"


class TestСвязьСЯдром:
    """ТЗ требует «связь с инцидентами и CAPA» — именно связь."""

    async def test_ссылка_на_расследование_необязательна(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пострадавших нет — инцидента не заводят, и пустая ссылка законна."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        assert body["incident_id"] is None
        assert body["follow_up"] == "not_started"

    async def test_ссылка_на_чужое_расследование_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        await _accident(
            async_client, headers, vehicle, incident_id="нет-такого", expect=404
        )

    async def test_привязка_к_расследованию_снимает_дыру_в_разборе(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        incident_id = await _incident(sessionmaker)
        body = await _accident(
            async_client, headers, vehicle, injured=1, incident_id=incident_id
        )
        assert body["incident_id"] == incident_id
        # мероприятий ещё нет, но расследование заведено — «не начато» это уже
        # неправда
        assert body["follow_up"] == "closed"

    async def test_ошибочную_привязку_можно_снять(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        incident_id = await _incident(sessionmaker)
        body = await _accident(
            async_client, headers, vehicle, incident_id=incident_id
        )
        response = await async_client.patch(
            f"{_API}/accidents/{body['id']}",
            json={"incident_id": None},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["incident_id"] is None


class TestРазборЧерезCAPA:
    """Своего статуса «разобрано» у ДТП НЕТ — он следует из мероприятий."""

    async def test_мероприятия_живут_в_ядровом_capa(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Своей таблицы мероприятий контур БДД не заводит.

        Ядро адресуется парой «тип источника + идентификатор» и принимает
        любую строку — правок ядра для этого не понадобилось ни одной.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        await _capa(sessionmaker, body["id"])
        listing = await async_client.get(f"{_API}/accidents", headers=headers)
        assert listing.status_code == 200, listing.text
        row = listing.json()["items"][0]
        assert row["capa_total"] == 1
        assert row["capa_open"] == 1
        assert row["follow_up"] == "open"
        assert row["follow_up_label"] == "Есть незакрытые мероприятия"

    async def test_закрытие_мероприятия_меняет_состояние_разбора(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Галочки «разобрано» нет: состояние пересчитывается по ядру.

        Была бы галочка — мероприятие закрыли бы, а её переставить забыли.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        await _capa(sessionmaker, body["id"], status="done")
        listing = await async_client.get(f"{_API}/accidents", headers=headers)
        row = listing.json()["items"][0]
        assert row["capa_total"] == 1
        assert row["capa_open"] == 0
        assert row["follow_up"] == "closed"
        assert row["follow_up_label"] == "Незакрытых мероприятий нет"

    async def test_мероприятия_чужого_источника_не_считаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: пара «тип + идентификатор» принимает любую строку, и без
        отбора по типу сюда попали бы мероприятия проверок и предписаний."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        body = await _accident(async_client, headers, vehicle)
        async with sessionmaker() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "test"))
            ).scalar_one()
            session.add(
                CorrectiveAction(
                    tenant_id=tenant.id,
                    source_type="inspection",
                    source_id=body["id"],
                    title="Чужое мероприятие",
                    action_type="corrective",
                    status="open",
                )
            )
            await session.commit()
        listing = await async_client.get(f"{_API}/accidents", headers=headers)
        row = listing.json()["items"][0]
        assert row["capa_total"] == 0
        assert row["follow_up"] == "not_started"


class TestРеестрИСводка:
    async def test_реестр_читается_от_свежих(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        now = datetime.now(timezone.utc)
        await _accident(
            async_client,
            headers,
            vehicle,
            place="старое",
            occurred_at=now - timedelta(days=30),
        )
        await _accident(
            async_client,
            headers,
            vehicle,
            place="свежее",
            occurred_at=now - timedelta(hours=2),
        )
        response = await async_client.get(f"{_API}/accidents", headers=headers)
        assert [row["place"] for row in response.json()["items"]] == [
            "свежее",
            "старое",
        ]

    async def test_отбор_по_виду_и_машине(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        other = await _vehicle(async_client, headers, plate="Е003ЕЕ99")
        await _accident(async_client, headers, vehicle, kind="collision")
        await _accident(async_client, headers, other, kind="rollover")
        response = await async_client.get(
            f"{_API}/accidents", params={"kind": "rollover"}, headers=headers
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["vehicle_plate"] == "Е003ЕЕ99"

    async def test_окно_сводки_годовое(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """У листов окно месячное, у ДТП — годовое: за месяц их обычно ноль."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        now = datetime.now(timezone.utc)
        await _accident(
            async_client,
            headers,
            vehicle,
            place="давно",
            occurred_at=now - timedelta(days=400),
        )
        await _accident(
            async_client,
            headers,
            vehicle,
            place="в этом году",
            occurred_at=now - timedelta(days=100),
            injured=2,
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["accident_window_days"] == 365
        assert body["accidents_total"] == 1
        assert body["injured_total"] == 2
        assert body["accidents_by_consequences"] == {
            "damage_only": 0,
            "injured": 1,
            "fatal": 0,
        }

    async def test_сводка_показывает_дыру_в_разборе(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        vehicle = await _vehicle(async_client, headers)
        without = await _accident(async_client, headers, vehicle, place="без разбора")
        with_capa = await _accident(
            async_client, headers, vehicle, place="с мероприятием"
        )
        await _capa(sessionmaker, with_capa["id"])
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["accidents_total"] == 2
        assert body["accidents_without_follow_up"] == 1
        assert without["follow_up"] == "not_started"

    async def test_вердикта_о_вине_и_достаточности_мер_в_сводке_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА-сторож: вину устанавливают ГИБДД и суд."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in (
                "our_fault_total",
                "measures_sufficient",
                "accident_rate_verdict",
                "compliant",
            )
        )
