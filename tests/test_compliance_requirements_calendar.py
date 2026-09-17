"""Контрольные даты требований реестра в общем календаре (B.18 разд. 19.2, срез-149).

ЗАЧЕМ. Разд. 19.2 требует у требования «периодичность и контрольные даты», а
разд. 57.2 — «всё в одном месте». Срез-145 завёл реестр требований со сроком,
но подключил его только к своему экрану и к Центру внимания, у которого
горизонт три дня. Общий календарь арендатора — место, где планируют месяц
вперёд, и в нём обязанностей по НПА не было вовсе: календарь знал перезарядку
огнетушителей и поверку тахографа, а «пересмотреть инструкции до 1 марта» —
нет. Специалист, открывший календарь, видел пустой март и узнавал о сроке за
три дня.

ЧТО ПРОВЕРЯЕТСЯ: контракт источника; в календарь попадает только требование
НА КОНТРОЛЕ и только со сроком; исполненное разовое и снятое с контроля —
нет; просрочка и полоса SLA; отбор по площадке и по окну дат; счётчики
источника; чужой арендатор не виден; источник не размечен дисциплиной (у
требования её нет) и не поимённый (ответственный — пользователь, а не
карточка сотрудника).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import (
    ATTENTION_SOURCES,
    PERSON_SCOPED_SOURCES,
    UNCLASSIFIED_SOURCES,
    discipline_of,
)
from app.models.compliance_requirements import ComplianceRequirement
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

SOURCE = "compliance_requirement"
#: Даты нарочно далеко от «сегодня»: «сегодня» у продукта по UTC, у процесса
#: тестов — по местному поясу, вечером это разные дни (срез-140/143).
TODAY = datetime.now(tz=timezone.utc).date()


def test_источник_объявлен_без_дисциплины_и_не_поимённый() -> None:
    assert SOURCE in ALL_SOURCES
    # Источник ЦЕЛИКОМ к одной дисциплине не относится: обязанность бывает
    # общей для арендатора (порядок расследования, режим труда и отдыха).
    # Причина названа словами, иначе сторож полноты разметки не пропустит.
    assert SOURCE in UNCLASSIFIED_SOURCES
    assert discipline_of(SOURCE) is None
    assert SOURCE not in ATTENTION_SOURCES
    # Ответственный — пользователь системы, а не карточка сотрудника: подменять
    # одно другим значило бы выдать чужое по фильтру «по человеку».
    assert SOURCE not in PERSON_SCOPED_SOURCES


def test_у_записи_с_процессом_дисциплина_есть() -> None:
    """Срез-196: то, ради чего процесс стал закрытым словарём.

    Пока процесс был свободной строкой, сроки, следующие из ЗАКОНА, не попадали
    ни в один дисциплинарный отчёт: «что у нас по пожарной безопасности»
    отвечало про тренировки и огнетушители и молчало про обязанность из приказа.
    """

    from app.core.disciplines import Discipline, discipline_of_event

    assert discipline_of_event(SOURCE, {"process_code": "fire_safety"}) is Discipline.FIRE_SAFETY
    # А у записи без процесса — по-прежнему нет, и это правда, а не пробел.
    assert discipline_of_event(SOURCE, {"process_code": None}) is None


def _requirement(tenant_id: str, *, code: str, **extra) -> ComplianceRequirement:
    extra.setdefault("title", "Проводить обучение по охране труда")
    extra.setdefault("status", "active")
    return ComplianceRequirement(tenant_id=tenant_id, code=code, **extra)


class TestКалендарь:
    async def test_на_контроле_со_сроком_видно_исполненное_и_снятое_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add_all(
            [
                _requirement(
                    tid,
                    code="ОТ-01",
                    title="Обучение руководителей",
                    next_due_at=TODAY - timedelta(days=10),
                    severity="critical",
                    periodicity_days=365,
                ),
                _requirement(
                    tid,
                    code="ОТ-02",
                    title="Пересмотр инструкций",
                    next_due_at=TODAY + timedelta(days=20),
                ),
                # Разовое исполнено: срок закрыт, в календаре ему не место.
                _requirement(
                    tid,
                    code="ОТ-03",
                    title="Разработать положение",
                    next_due_at=TODAY + timedelta(days=5),
                    status="fulfilled",
                ),
                # Снято с контроля: остаётся в реестре, но срока больше нет.
                _requirement(
                    tid,
                    code="ОТ-04",
                    title="Отменённая обязанность",
                    next_due_at=TODAY + timedelta(days=5),
                    status="retired",
                ),
                # Без контрольной даты: события без даты не бывает.
                _requirement(tid, code="ОТ-05", title="Без срока"),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(source_types=[SOURCE], include_sla=True)

        titles = {item.title for item in response.items}
        assert titles == {
            "Требование ОТ-01: Обучение руководителей",
            "Требование ОТ-02: Пересмотр инструкций",
        }
        overdue_item = next(i for i in response.items if i.extra["code"] == "ОТ-01")
        assert overdue_item.is_overdue is True
        assert overdue_item.status == "overdue"
        assert overdue_item.sla_band == "overdue"
        assert overdue_item.extra["severity"] == "critical"
        assert overdue_item.extra["periodicity_days"] == 365
        assert overdue_item.source_id
        calm = next(i for i in response.items if i.extra["code"] == "ОТ-02")
        assert calm.is_overdue is False
        assert calm.status == "valid"
        # 20 дней до срока — внешняя полоса (14, 30), а не «критично».
        assert calm.sla_band == "warning"

        (count,) = [c for c in response.by_source if c.source_type == SOURCE]
        assert count.count == 2
        assert count.overdue_count == 1

    async def test_отбор_по_площадке_и_окну_дат(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        company = await data_factory.create_company(
            tenant=tenant, name="АКМЕ Календарь", session=test_db_session
        )
        from app.models.master_data import Site

        site = Site(tenant_id=tid, company_id=company.id, name="Цех №1")
        other = Site(tenant_id=tid, company_id=company.id, name="Склад")
        test_db_session.add_all([site, other])
        await test_db_session.flush()
        test_db_session.add_all(
            [
                _requirement(
                    tid,
                    code="ПЛ-01",
                    title="Проверка заземления цеха",
                    next_due_at=TODAY + timedelta(days=3),
                    site_id=site.id,
                ),
                _requirement(
                    tid,
                    code="ПЛ-02",
                    title="Проверка склада",
                    next_due_at=TODAY + timedelta(days=3),
                    site_id=other.id,
                ),
                _requirement(
                    tid,
                    code="ПЛ-03",
                    title="Далёкий срок",
                    next_due_at=TODAY + timedelta(days=200),
                    site_id=site.id,
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        by_site = await service.list_events(source_types=[SOURCE], site_id=site.id)
        assert {i.extra["code"] for i in by_site.items} == {"ПЛ-01", "ПЛ-03"}
        assert all(i.site_id == site.id for i in by_site.items)
        (site_count,) = [c for c in by_site.by_source if c.source_type == SOURCE]
        assert site_count.count == 2

        windowed = await service.list_events(
            source_types=[SOURCE],
            from_at=datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc),
            to_at=datetime.combine(
                TODAY + timedelta(days=30), datetime.min.time(), tzinfo=timezone.utc
            ),
        )
        assert {i.extra["code"] for i in windowed.items} == {"ПЛ-01", "ПЛ-02"}
        (window_count,) = [c for c in windowed.by_source if c.source_type == SOURCE]
        assert window_count.count == 2

    async def test_чужой_арендатор_не_виден(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        mine = await data_factory.ensure_tenant(session=test_db_session)
        theirs = await data_factory.ensure_tenant(slug="neighbour", session=test_db_session)
        test_db_session.add_all(
            [
                _requirement(
                    str(mine.id),
                    code="МОЁ-01",
                    title="Моё требование",
                    next_due_at=TODAY + timedelta(days=7),
                ),
                _requirement(
                    str(theirs.id),
                    code="ЧУЖОЕ-01",
                    title="Чужое требование",
                    next_due_at=TODAY + timedelta(days=7),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(mine.id), db=test_db_session)
        response = await service.list_events(source_types=[SOURCE])
        assert {i.extra["code"] for i in response.items} == {"МОЁ-01"}

    async def test_в_общей_выдаче_без_фильтра_источник_тоже_есть(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Источник должен работать и когда его не запрашивали явно: именно так
        календарь открывается по умолчанию."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        test_db_session.add(
            _requirement(
                tid,
                code="ОБЩ-01",
                title="Требование в общей выдаче",
                next_due_at=TODAY + timedelta(days=2),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events()
        assert any(
            item.source_type == SOURCE and item.extra["code"] == "ОБЩ-01" for item in response.items
        )
        assert any(c.source_type == SOURCE and c.count == 1 for c in response.by_source)


class TestГраницы:
    async def test_дата_без_времени_приводится_к_utc_полуночи(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """У требования срок — дата (не момент). Календарь сортирует и сравнивает
        по времени, поэтому дата обязана стать полуночью UTC, а не «полуночью
        часового пояса процесса»."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        due = date(2999, 1, 15)
        test_db_session.add(_requirement(tid, code="UTC-01", title="Далёкий срок", next_due_at=due))
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(source_types=[SOURCE])
        (item,) = [i for i in response.items if i.extra["code"] == "UTC-01"]
        assert item.starts_at == datetime(2999, 1, 15, tzinfo=timezone.utc)
        assert item.ends_at is None
        # «Факта» у требования нет: подтверждение двигает сам срок.
        assert item.actual_at is None
        assert item.variance_days is None
