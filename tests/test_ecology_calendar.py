"""Контур экологии срез-7 (Доп. №1 разд. 55.3): экологический календарь.

Требование: «Экологический календарь: сроки сдачи отчётности, платежей,
замеров, продления разрешений — в общий календарь и Attention Center».

СВЕРКА нашла два расхождения:

1. **Экологии не было в календаре вовсе.** Срезы 1–6 завели сроки (разрешения
   на выброс, разрешения водопользования, плановые даты замеров ПЭК), но ни
   один из них не доходил до общего календаря: ``ALL_SOURCES`` не знал про
   экологию, и в Attention Center дисциплина не появлялась ни разу.
2. **Фронт отстал от бэкенда на один источник.** В ``CALENDAR_SOURCE_TYPES``
   (frontend/src/types/dto/calendar.ts) не было ``medical_referral``, хотя
   бэкенд отдаёт его с самого начала. Дрейф молчаливый: список на фронте
   написан руками, и никто не сверял его с ``ALL_SOURCES``.

Решения:

* **два источника, а не один**: «продление разрешений» и «замеры» — разные
  задачи эколога, и смешать их значило бы отнять возможность отфильтровать;
* **разрешения на выброс и на водопользование — ОДИН источник**: для эколога
  это один вопрос «что продлевать», и оба срока живут по одному правилу;
* **бессрочное разрешение в календарь не попадает**: события без даты не
  бывает, а придумывать дату — враньё. Пустой срок означает «бессрочно» с
  среза-3, и календарь обязан это уважать;
* **сроки отчётности и платежей идут через существующий контур сроков**
  (``compliance_deadline``), а не через выдуманные платформой даты: 20-е число
  и 10 марта установлены законом, и вшивать их в код значило бы подменять
  нормативный акт (та же граница, что у периодичности ПЭК).

ГРАНИЦА: платформа не изобретает сроки — она показывает те, что уже внесены в
разрешениях и плане-графике ПЭК.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline, discipline_of
from app.models.ecology import (
    EmissionMonitoringPlanItem,
    EmissionNorm,
    EmissionSource,
    EnvironmentalFacility,
    WaterUsagePoint,
)
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

_ECOLOGY_SOURCES = ("ecology_permit", "ecology_measurement")


async def _facility(session: AsyncSession, tenant_id: str) -> EnvironmentalFacility:
    facility = EnvironmentalFacility(
        tenant_id=tenant_id,
        name="Производственная площадка",
        register_number="12-0177-010001-П",
        category="II",
        status="registered",
    )
    session.add(facility)
    await session.flush()
    return facility


async def _source(
    session: AsyncSession, tenant_id: str, facility_id: str
) -> EmissionSource:
    source = EmissionSource(
        tenant_id=tenant_id,
        facility_id=facility_id,
        source_number="0001",
        name="Труба котельной",
        kind="organized",
    )
    session.add(source)
    await session.flush()
    return source


class TestИсточникиЭкологииВКалендаре:
    async def test_источники_объявлены_и_размечены_дисциплиной(self) -> None:
        """Без разметки запись попала бы в «не классифицировано»."""

        for code in _ECOLOGY_SOURCES:
            assert code in ALL_SOURCES, code
            assert discipline_of(code) is Discipline.ECOLOGY, code

    async def test_срок_разрешения_на_выброс_попадает_в_календарь(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        source = await _source(test_db_session, str(tenant.id), facility.id)
        test_db_session.add(
            EmissionNorm(
                tenant_id=str(tenant.id),
                source_id=source.id,
                substance="Азота диоксид",
                limit_grams_per_second=Decimal("0.025000"),
                permit_number="РВ-77-000123",
                valid_until=date.today() + timedelta(days=40),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_permit"])
        assert response.total == 1
        item = response.items[0]
        assert item.source_type == "ecology_permit"
        assert "Азота диоксид" in item.title
        assert item.is_overdue is False

    async def test_бессрочное_разрешение_в_календарь_не_попадает(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """События без даты не бывает, а придумывать дату — враньё."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        source = await _source(test_db_session, str(tenant.id), facility.id)
        test_db_session.add(
            EmissionNorm(
                tenant_id=str(tenant.id),
                source_id=source.id,
                substance="Углерода оксид",
                limit_tons_per_year=Decimal("1.200"),
                valid_until=None,
            )
        )
        test_db_session.add(
            WaterUsagePoint(
                tenant_id=str(tenant.id),
                facility_id=facility.id,
                point_number="В-1",
                name="Скважина №1",
                kind="intake",
                permit_valid_until=None,
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_permit"])
        assert response.total == 0
        assert response.items == []

    async def test_разрешение_водопользования_в_том_же_источнике(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Для эколога продление разрешений — один вопрос, а не два."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        test_db_session.add(
            WaterUsagePoint(
                tenant_id=str(tenant.id),
                facility_id=facility.id,
                point_number="В-1",
                name="Скважина №1",
                kind="intake",
                permit_number="МОС-00123-ВХ",
                permit_valid_until=date.today() + timedelta(days=20),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_permit"])
        assert response.total == 1
        assert "Скважина №1" in response.items[0].title

    async def test_просроченное_разрешение_помечено_просрочкой(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        test_db_session.add(
            WaterUsagePoint(
                tenant_id=str(tenant.id),
                facility_id=facility.id,
                point_number="В-1",
                name="Скважина №1",
                kind="intake",
                permit_valid_until=date.today() - timedelta(days=5),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_permit"])
        assert response.items[0].is_overdue is True
        assert response.overdue_count == 1

    async def test_плановый_замер_пэк_попадает_в_календарь(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        source = await _source(test_db_session, str(tenant.id), facility.id)
        test_db_session.add(
            EmissionMonitoringPlanItem(
                tenant_id=str(tenant.id),
                source_id=source.id,
                substance="Азота диоксид",
                periodicity_months=3,
                next_due_on=date.today() + timedelta(days=10),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_measurement"])
        assert response.total == 1
        item = response.items[0]
        assert item.source_type == "ecology_measurement"
        assert "Азота диоксид" in item.title

    async def test_замеры_и_разрешения_фильтруются_порознь(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Разные задачи эколога: продлить документ и заказать замер."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        source = await _source(test_db_session, str(tenant.id), facility.id)
        test_db_session.add(
            EmissionMonitoringPlanItem(
                tenant_id=str(tenant.id),
                source_id=source.id,
                substance="Азота диоксид",
                periodicity_months=3,
                next_due_on=date.today() + timedelta(days=10),
            )
        )
        test_db_session.add(
            WaterUsagePoint(
                tenant_id=str(tenant.id),
                facility_id=facility.id,
                point_number="В-1",
                name="Скважина №1",
                kind="intake",
                permit_valid_until=date.today() + timedelta(days=30),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        only_permits = await service.list_events(source_types=["ecology_permit"])
        assert only_permits.total == 1
        only_measurements = await service.list_events(
            source_types=["ecology_measurement"]
        )
        assert only_measurements.total == 1
        both = await service.list_events(source_types=list(_ECOLOGY_SOURCES))
        assert both.total == 2

    async def test_чужой_арендатор_не_видит_сроков(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        facility = await _facility(test_db_session, str(tenant.id))
        test_db_session.add(
            WaterUsagePoint(
                tenant_id=str(tenant.id),
                facility_id=facility.id,
                point_number="В-1",
                name="Скважина №1",
                kind="intake",
                permit_valid_until=date.today() + timedelta(days=30),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(
            tenant_id="00000000-0000-0000-0000-000000000000", db=test_db_session
        )
        response = await service.list_events(source_types=["ecology_permit"])
        assert response.total == 0

    async def test_счётчики_источников_приходят_всегда(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Ноль по источнику должен отличаться от «источник не пришёл»."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = CalendarAggregatorService(
            tenant_id=str(tenant.id), db=test_db_session
        )
        response = await service.list_events()
        codes = {row.source_type for row in response.by_source}
        assert set(_ECOLOGY_SOURCES) <= codes


class TestСторожСпискаИсточников:
    """Сторож против молчаливого дрейфа фронта: список источников написан на

    фронте руками, и его никто не сверял с ``ALL_SOURCES``. Из-за этого
    ``medical_referral`` отсутствовал там с самого начала — бэкенд отдавал
    источник, а фронт про него не знал.
    """

    def test_список_источников_на_фронте_совпадает_с_бэкендом(self) -> None:
        path = (
            Path(__file__).resolve().parents[1]
            / "frontend"
            / "src"
            / "types"
            / "dto"
            / "calendar.ts"
        )
        text = path.read_text(encoding="utf-8")
        block = re.search(
            r"CALENDAR_SOURCE_TYPES:\s*readonly CalendarSourceType\[\]\s*=\s*\[(.*?)\]",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся список CALENDAR_SOURCE_TYPES"
        front = set(re.findall(r'"([a-z_]+)"', block.group(1)))
        assert front == set(ALL_SOURCES), sorted(front ^ set(ALL_SOURCES))
