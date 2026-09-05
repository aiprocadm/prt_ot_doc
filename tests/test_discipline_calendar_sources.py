"""Сроки ПромБез, ГО и БДД в общем календаре (BIZ-54-57 срез-57, Доп. №1 разд. 57.2).

Требование: «Центр внимания агрегирует просрочки и риски по всем контурам:
… просрочена ЭПБ на ОПО, … просрочен техосмотр ТС, не проведены учения по ГО».

СВЕРКА нашла: у трёх дисциплин не было НИ ОДНОГО источника в календарном
агрегаторе. Модули ПромБез, ГО и БДД считали свои сроки каждый у себя, а
общий календарь и Центр внимания о них не знали — три из пяти примеров
разд. 57.2 не работали.

Решения — по образцу экологического календаря (срез-7):

* по ОДНОМУ источнику на дисциплину: ЭПБ устройств, учения ГО, документы ТС;
  четыре срока машины (техосмотр, ОСАГО, лицензия, тахограф) — один источник
  с видом в ``extra.kind``: для ответственного за БДД это один вопрос «что по
  машинам истекает»;
* правила ТЕ ЖЕ, что у модулей: списанное ТС и выведенное из эксплуатации
  устройство просрочкой быть не могут; проведённое учение — протокол, а не
  срок; пустая дата — «сведений нет» / «заключения нет», а не срок;
* поверка тахографа — только если тахограф установлен: иначе календарь
  требовал бы поверить прибор, которого нет.

ГРАНИЦА: платформа не изобретает сроки — показывает внесённые в реестрах.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline, discipline_of
from app.models.civil_defense import CivilDefenseDrill
from app.models.industrial_safety import HazardousFacility, TechnicalDevice
from app.models.master_data import Person
from app.models.models import Company
from app.models.road_safety import Driver, Vehicle
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

_SOURCES = {
    "industrial_safety_epb": Discipline.INDUSTRIAL_SAFETY,
    "civil_defense_drill": Discipline.CIVIL_DEFENSE,
    "road_safety_vehicle": Discipline.ROAD_SAFETY,
    # срез-59 (разд. 56.2): поимённый срок БДД — водительское удостоверение
    "road_safety_driver": Discipline.ROAD_SAFETY,
}

TODAY = date.today()


async def _device(
    session: AsyncSession,
    tenant_id: str,
    *,
    name: str,
    valid_until: date | None,
    status="in_operation",
) -> TechnicalDevice:
    facility = HazardousFacility(
        tenant_id=tenant_id, name="Котельная", register_number=f"А01-{name}", hazard_class="III"
    )
    session.add(facility)
    await session.flush()
    device = TechnicalDevice(
        tenant_id=tenant_id,
        facility_id=facility.id,
        kind="boiler",
        name=name,
        epb_valid_until=valid_until,
        status=status,
    )
    session.add(device)
    await session.flush()
    return device


def _drill(tenant_id: str, *, planned_on: date, held_on: date | None = None, site_id=None):
    return CivilDefenseDrill(
        tenant_id=tenant_id,
        kind="evacuation",
        title="Тренировка по эвакуации",
        planned_on=planned_on,
        held_on=held_on,
        site_id=site_id,
    )


def _vehicle(tenant_id: str, plate: str, **fields) -> Vehicle:
    return Vehicle(
        tenant_id=tenant_id, plate_number=plate, brand_model="ГАЗель", kind="truck", **fields
    )


async def _driver(
    session: AsyncSession,
    tenant_id: str,
    *,
    last_name: str,
    license_due: date | None,
    status: str = "admitted",
) -> Driver:
    company = (
        (await session.execute(select(Company).where(Company.tenant_id == tenant_id)))
        .scalars()
        .first()
    )
    if company is None:
        company = Company(tenant_id=tenant_id, name="ООО Автобаза")
        session.add(company)
        await session.flush()
    person = Person(
        tenant_id=tenant_id, company_id=company.id, first_name="Пётр", last_name=last_name
    )
    session.add(person)
    await session.flush()
    driver = Driver(
        tenant_id=tenant_id,
        person_id=person.id,
        license_number=f"77 {last_name}",
        categories=["B", "C"],
        license_due=license_due,
        status=status,
    )
    session.add(driver)
    await session.flush()
    return driver


def _service(tenant_id: str, session: AsyncSession) -> CalendarAggregatorService:
    return CalendarAggregatorService(tenant_id=tenant_id, db=session)


class TestИсточникиОбъявлены:
    async def test_источники_объявлены_и_размечены_дисциплиной(self) -> None:
        """Без разметки запись попала бы в «не классифицировано»."""

        for code, discipline in _SOURCES.items():
            assert code in ALL_SOURCES, code
            assert discipline_of(code) is discipline, code

    async def test_счётчики_источников_приходят_всегда(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        response = await _service(str(tenant.id), test_db_session).list_events()
        assert set(_SOURCES) <= {row.source_type for row in response.by_source}


class TestЭПБ:
    async def test_срок_эпб_попадает_в_календарь(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _device(
            test_db_session, str(tenant.id), name="Котёл №1", valid_until=TODAY + timedelta(days=40)
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["industrial_safety_epb"], include_sla=True
        )
        assert response.total == 1
        item = response.items[0]
        assert item.source_type == "industrial_safety_epb"
        assert item.title == "ЭПБ: Котёл №1"
        assert item.is_overdue is False
        # 40 дней — внутри окна «критично» (30/90): экспертизу заказывают за месяцы
        assert item.sla_band == "warning"
        assert item.extra["epb_valid_until"] == (TODAY + timedelta(days=40)).isoformat()

    async def test_просроченная_эпб_помечена_просрочкой(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _device(
            test_db_session, str(tenant.id), name="Сосуд", valid_until=TODAY - timedelta(days=5)
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["industrial_safety_epb"]
        )
        assert response.items[0].is_overdue is True
        assert response.items[0].status == "expired"
        assert response.by_source[0].overdue_count == 1

    async def test_без_заключения_и_списанное_в_календарь_не_попадают(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """«Заключения нет» — не срок; списанное устройство — не просрочка (как в модуле)."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _device(test_db_session, str(tenant.id), name="Новый", valid_until=None)
        await _device(
            test_db_session,
            str(tenant.id),
            name="Списанный",
            valid_until=TODAY - timedelta(days=100),
            status="decommissioned",
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["industrial_safety_epb"]
        )
        assert response.total == 0
        assert response.by_source[0].overdue_count == 0


class TestУченияГО:
    async def test_непроведённое_учение_в_прошлом_это_просрочка(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(_drill(str(tenant.id), planned_on=TODAY - timedelta(days=3)))
        test_db_session.add(_drill(str(tenant.id), planned_on=TODAY + timedelta(days=10)))
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["civil_defense_drill"]
        )
        assert response.total == 2
        assert [item.is_overdue for item in response.items] == [True, False]
        assert response.items[0].title == "Учение ГО: Тренировка по эвакуации"
        assert response.items[0].status == "overdue"
        assert response.items[1].status == "planned"
        assert response.by_source[0].overdue_count == 1

    async def test_проведённое_учение_это_протокол_а_не_срок(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(
            _drill(
                str(tenant.id),
                planned_on=TODAY - timedelta(days=30),
                held_on=TODAY - timedelta(days=30),
            )
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["civil_defense_drill"]
        )
        assert response.total == 0

    async def test_сужение_по_площадке(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        site = await data_factory.create_site(tenant=tenant, session=test_db_session)
        test_db_session.add(
            _drill(str(tenant.id), planned_on=TODAY + timedelta(days=5), site_id=site.id)
        )
        test_db_session.add(_drill(str(tenant.id), planned_on=TODAY + timedelta(days=6)))
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["civil_defense_drill"], site_id=str(site.id)
        )
        assert response.total == 1
        assert response.items[0].site_id == str(site.id)


class TestДокументыТС:
    async def test_четыре_срока_машины_в_одном_источнике(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(
            _vehicle(
                str(tenant.id),
                "А123БВ77",
                inspection_due=TODAY - timedelta(days=2),
                insurance_due=TODAY + timedelta(days=20),
                license_due=TODAY + timedelta(days=200),
                tachograph_installed=True,
                tachograph_due=TODAY + timedelta(days=5),
            )
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["road_safety_vehicle"], include_sla=True
        )
        assert response.total == 4
        by_kind = {item.extra["kind"]: item for item in response.items}
        assert set(by_kind) == {"inspection", "insurance", "license", "tachograph"}
        assert by_kind["inspection"].title == "Техосмотр ТС: А123БВ77"
        assert by_kind["inspection"].is_overdue is True
        assert by_kind["tachograph"].title == "Поверка тахографа: А123БВ77"
        assert by_kind["tachograph"].sla_band == "critical"
        assert by_kind["insurance"].sla_band == "warning"
        # хронология: просроченный техосмотр первым
        assert [item.extra["kind"] for item in response.items][0] == "inspection"
        assert response.by_source[0].overdue_count == 1
        # у каждого срока свой id — иначе четыре события одной машины слиплись бы
        assert len({item.id for item in response.items}) == 4

    async def test_пустая_дата_и_тахограф_без_прибора_не_сроки(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(
            _vehicle(
                str(tenant.id),
                "В456ГД77",
                inspection_due=None,
                tachograph_installed=False,
                tachograph_due=TODAY - timedelta(days=10),
            )
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["road_safety_vehicle"]
        )
        assert response.total == 0
        assert response.by_source[0].overdue_count == 0

    async def test_списанная_машина_не_просрочка(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        test_db_session.add(
            _vehicle(
                str(tenant.id),
                "Е789ЖЗ77",
                status="decommissioned",
                inspection_due=TODAY - timedelta(days=90),
            )
        )
        test_db_session.add(
            _vehicle(
                str(tenant.id),
                "И012КЛ77",
                status="suspended",
                inspection_due=TODAY - timedelta(days=90),
            )
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["road_safety_vehicle"]
        )
        assert response.total == 0

    async def test_сужение_по_площадке_и_окну(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        site = await data_factory.create_site(tenant=tenant, session=test_db_session)
        test_db_session.add(
            _vehicle(
                str(tenant.id),
                "М345НО77",
                site_id=site.id,
                inspection_due=TODAY + timedelta(days=3),
                insurance_due=TODAY + timedelta(days=400),
            )
        )
        test_db_session.add(
            _vehicle(str(tenant.id), "П678РС77", inspection_due=TODAY + timedelta(days=3))
        )
        await test_db_session.commit()

        service = _service(str(tenant.id), test_db_session)
        by_site = await service.list_events(
            source_types=["road_safety_vehicle"], site_id=str(site.id)
        )
        assert by_site.total == 2
        assert all(item.site_id == str(site.id) for item in by_site.items)
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        windowed = await service.list_events(
            source_types=["road_safety_vehicle"],
            site_id=str(site.id),
            from_at=now - timedelta(days=1),
            to_at=now + timedelta(days=30),
        )
        # счётчик источника считает в ТОМ ЖЕ окне, что и список
        assert windowed.total == 1
        assert windowed.by_source[0].count == 1


class TestВодительскиеУдостоверения:
    """Срез-59 (разд. 56.2): поимённый срок БДД — правила те же, что у
    готовности модуля: только допущенные, пустая дата — «сведений нет»."""

    async def test_срок_удостоверения_попадает_в_календарь_с_человеком(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        driver = await _driver(
            test_db_session,
            str(tenant.id),
            last_name="Шофёров",
            license_due=TODAY - timedelta(days=2),
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["road_safety_driver"], include_sla=True
        )
        assert response.total == 1
        item = response.items[0]
        assert item.source_type == "road_safety_driver"
        assert item.title == "Водительское удостоверение: Шофёров Пётр"
        assert item.person_id == str(driver.person_id)
        assert item.is_overdue is True and item.status == "expired"
        assert item.sla_band == "overdue"
        assert item.extra["license_number"] == "77 Шофёров"
        assert item.extra["categories"] == ["B", "C"]
        source = response.by_source[0]
        assert (source.count, source.overdue_count) == (1, 1)

    async def test_отстранённый_уволенный_и_без_даты_не_считаются(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        await _driver(
            test_db_session, tid, last_name="Допущенный", license_due=TODAY + timedelta(days=5)
        )
        await _driver(
            test_db_session,
            tid,
            last_name="Отстранённый",
            license_due=TODAY - timedelta(days=5),
            status="suspended",
        )
        await _driver(
            test_db_session,
            tid,
            last_name="Уволенный",
            license_due=TODAY - timedelta(days=5),
            status="dismissed",
        )
        await _driver(test_db_session, tid, last_name="Безсведений", license_due=None)
        await test_db_session.commit()

        response = await _service(tid, test_db_session).list_events(
            source_types=["road_safety_driver"]
        )
        assert [item.title for item in response.items] == [
            "Водительское удостоверение: Допущенный Пётр"
        ]
        source = response.by_source[0]
        assert (source.count, source.overdue_count) == (1, 0)

    async def test_сужение_до_человека_отдаёт_только_его(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Источник поимённый: чужое удостоверение в личный список не попадает."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        mine = await _driver(
            test_db_session, tid, last_name="Свой", license_due=TODAY - timedelta(days=1)
        )
        await _driver(
            test_db_session, tid, last_name="Чужой", license_due=TODAY - timedelta(days=1)
        )
        await test_db_session.commit()

        response = await _service(tid, test_db_session).list_events(
            source_types=["road_safety_driver"], person_id=str(mine.person_id)
        )
        assert [item.person_id for item in response.items] == [str(mine.person_id)]
        source = response.by_source[0]
        assert (source.count, source.overdue_count) == (1, 1)


class TestЧужойАрендатор:
    async def test_чужой_арендатор_не_видит_сроков(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _device(
            test_db_session, str(tenant.id), name="Кран", valid_until=TODAY + timedelta(days=10)
        )
        test_db_session.add(_drill(str(tenant.id), planned_on=TODAY + timedelta(days=1)))
        test_db_session.add(
            _vehicle(str(tenant.id), "Т901УФ77", inspection_due=TODAY + timedelta(days=1))
        )
        await _driver(
            test_db_session,
            str(tenant.id),
            last_name="Чужак",
            license_due=TODAY + timedelta(days=1),
        )
        await test_db_session.commit()

        response = await _service(
            "00000000-0000-0000-0000-000000000000", test_db_session
        ).list_events(source_types=list(_SOURCES))
        assert response.total == 0
