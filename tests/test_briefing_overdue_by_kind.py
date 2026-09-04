"""Просрочки инструктажей по видам (BIZ-54-57 срез-58, Доп. №1 разд. 54.1 / 57.2).

Требование 57.2: Центр внимания агрегирует просрочки «по всем контурам».
Требование 54.1: противопожарные инструктажи и ПТМ — с контролем сроков.

СВЕРКА нашла: вид инструктажа уже размечен дисциплиной (срез ПБ-3), но
общий календарь отдавал по источнику ОДНО число просрочек, и центр внимания
относил его целиком к «Обучению» — умолчанию источника. Просроченный ПТМ в
строке «Пожарная безопасность» не показывался никогда, а сама строка
считалась «без источника сроков».

Решение: агрегатор отдаёт те же просрочки, разложенные по виду записи
(``overdue_by_kind``), а формула дисциплин раскладывает виды по словарю.
Списки при этом не пересчитываются — это ещё один COUNT с теми же фильтрами.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import Discipline
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.master_data import Person
from app.models.models import Company
from app.services.calendar_aggregator import CalendarAggregatorService
from app.services.discipline_attention import ATTENTION_DISCIPLINES, overdue_by_discipline
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

NOW = datetime.now(timezone.utc)


async def _seed(session: AsyncSession, tenant_id: str) -> tuple[str, str]:
    """Два человека: у первого — ПТМ, повторный по ОТ и предрейсовый (все
    просрочены) плюс один действующий противопожарный; у второго — один
    просроченный ПТМ. Возвращает их id."""

    company = Company(tenant_id=tenant_id, name="ООО Инструктажи")
    session.add(company)
    await session.flush()
    first = Person(
        tenant_id=tenant_id, company_id=company.id, first_name="Анна", last_name="Первая"
    )
    second = Person(
        tenant_id=tenant_id, company_id=company.id, first_name="Борис", last_name="Второй"
    )
    journal = BriefingJournal(tenant_id=tenant_id, code="J-1", title="Журнал", journal_type="fire")
    session.add_all([first, second, journal])
    await session.flush()

    def entry(person: Person, kind: str, *, valid_days: int) -> BriefingEntry:
        return BriefingEntry(
            tenant_id=tenant_id,
            briefing_journal_id=journal.id,
            person_id=person.id,
            briefing_type=kind,
            briefing_date=NOW - timedelta(days=100),
            valid_until=NOW + timedelta(days=valid_days),
            status="done",
        )

    session.add_all(
        [
            entry(first, "fire_ptm", valid_days=-35),
            entry(first, "repeat", valid_days=-20),
            entry(first, "road_pre_trip", valid_days=-1),
            entry(first, "fire_repeat", valid_days=+30),  # действует — не просрочка
            entry(second, "fire_ptm", valid_days=-5),
        ]
    )
    await session.commit()
    return str(first.id), str(second.id)


def _service(tenant_id: str, session: AsyncSession) -> CalendarAggregatorService:
    return CalendarAggregatorService(tenant_id=tenant_id, db=session)


class TestАгрегатор:
    async def test_просрочки_разложены_по_видам_и_сходятся_с_итогом(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _seed(test_db_session, str(tenant.id))

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["briefing_entry"]
        )

        source = next(row for row in response.by_source if row.source_type == "briefing_entry")
        assert source.count == 5
        assert source.overdue_count == 4
        assert source.overdue_by_kind == {"fire_ptm": 2, "repeat": 1, "road_pre_trip": 1}
        assert sum(source.overdue_by_kind.values()) == source.overdue_count

    async def test_фильтр_по_человеку_режет_и_разложение(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Личный список — личные просрочки: чужой ПТМ в разложение не входит."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        _first, second = await _seed(test_db_session, str(tenant.id))

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["briefing_entry"], person_id=second
        )

        source = next(row for row in response.by_source if row.source_type == "briefing_entry")
        assert source.overdue_count == 1
        assert source.overdue_by_kind == {"fire_ptm": 1}

    async def test_окно_дат_применяется_к_разложению(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Окно центра внимания — те же фильтры, что у списка и у итога."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _seed(test_db_session, str(tenant.id))

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["briefing_entry"], from_at=NOW - timedelta(days=10)
        )

        source = next(row for row in response.by_source if row.source_type == "briefing_entry")
        assert source.overdue_count == 2  # предрейсовый (−1) и второй ПТМ (−5)
        assert source.overdue_by_kind == {"fire_ptm": 1, "road_pre_trip": 1}

    async def test_у_источников_по_таблице_разложения_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """``None`` — «источник по видам не делится», а не пустой словарь."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["medical_exam", "briefing_entry"]
        )
        by_source = {row.source_type: row for row in response.by_source}
        assert by_source["medical_exam"].overdue_by_kind is None
        assert by_source["briefing_entry"].overdue_by_kind == {}


class TestФормулаДисциплин:
    async def test_пожарные_виды_в_пожарную_безопасность_остальные_по_словарю(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _seed(test_db_session, str(tenant.id))

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["briefing_entry", "medical_exam"]
        )

        assert overdue_by_discipline(response) == {
            Discipline.FIRE_SAFETY: 2,
            Discipline.TRAINING: 1,
            Discipline.ROAD_SAFETY: 1,
        }
        assert Discipline.FIRE_SAFETY in ATTENTION_DISCIPLINES

    async def test_чужой_вид_никуда_не_относится(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Запись с видом вне словаря (унаследованная свободная строка) — не
        «обучение по умолчанию»: приписывать дисциплину нечему. Итог источника
        её при этом честно содержит — она не пропала, она не размечена."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        await _seed(test_db_session, str(tenant.id))
        journal = BriefingJournal(
            tenant_id=str(tenant.id), code="J-OLD", title="Старый", journal_type="general"
        )
        test_db_session.add(journal)
        await test_db_session.flush()
        test_db_session.add(
            BriefingEntry(
                tenant_id=str(tenant.id),
                briefing_journal_id=journal.id,
                briefing_type="по пожарке",
                briefing_date=NOW - timedelta(days=100),
                valid_until=NOW - timedelta(days=3),
                status="done",
            )
        )
        await test_db_session.commit()

        response = await _service(str(tenant.id), test_db_session).list_events(
            source_types=["briefing_entry"]
        )

        source = response.by_source[0]
        assert source.overdue_count == 5
        assert source.overdue_by_kind["по пожарке"] == 1
        assert overdue_by_discipline(response) == {
            Discipline.FIRE_SAFETY: 2,
            Discipline.TRAINING: 1,
            Discipline.ROAD_SAFETY: 1,
        }
