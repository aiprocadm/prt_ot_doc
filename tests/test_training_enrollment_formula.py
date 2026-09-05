"""«Просроченное назначение обучения» — одна формула на всю платформу (срез-77).

ЗАЧЕМ. Срок назначения (``TrainingEnrollment.due_at``, контур обучение-next)
считали шесть мест по отдельности: цифры дисциплины (``discipline_numbers``),
блокер готовности и рабочий стол роли (``routes/workspace``), внимание и
календарь сервисного центра (``domains/managed_clients``), операционный
дашборд (``modules/operational_dashboard``). А общий календарь и Центр
внимания о сроке назначения не знали вовсе: их источник ``training_session``
читает старую модель занятий. Блокер готовности кричал «просроченные
назначения», строка «Обучение» в Центре внимания рядом молчала — разд. 57.2
(«всё в одном месте», «одна формула»).

ЧТО ПРОВЕРЯЕТСЯ: сторож — никто в ``backend/app`` не пишет условие по статусу
или сроку назначения сам; календарь — живое просроченное назначение видно,
сданное/проваленное/удалённое/без срока — нет; отбор по человеку; живьём —
Центр внимания показывает назначение строкой «Обучение», и его цифра совпадает
с блокером готовности.
"""

from __future__ import annotations

import pathlib
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import (
    ATTENTION_SOURCES,
    PERSON_SCOPED_SOURCES,
    Discipline,
    discipline_of,
)
from app.models.models import RoleEnum, TrainingEnrollment, TrainingProgram
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio

REPO = pathlib.Path(__file__).resolve().parents[1]
APP = REPO / "backend" / "app"

#: Единственное место, где формула НАПИСАНА; остальные обязаны её импортировать.
FORMULA_HOME = "services/discipline_training.py"

_CONDITION = re.compile(r"TrainingEnrollment\.(status\.in_\(|due_at\s*<[^=])")

NOW = datetime.now(timezone.utc)


def test_сторож_условие_по_назначению_обучения_пишется_один_раз() -> None:
    """Своя копия формулы разойдётся с остальными на первой правке словаря."""

    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(APP).as_posix()
        if rel.startswith("migrations/") or rel == FORMULA_HOME:
            continue
        text = path.read_text(encoding="utf-8")
        if not _CONDITION.search(text):
            continue
        # PWA-карточки отбирают «живые» назначения тем же словарём — это импорт, не копия
        if "ACTIVE_ENROLLMENT_STATUSES" in text and "discipline_training" in text:
            continue
        offenders.append(rel)
    assert offenders == [], (
        "условие по назначению обучения написано заново — возьмите "
        f"overdue_training_enrollment_where из {FORMULA_HOME}: {offenders}"
    )


def test_источник_объявлен_размечен_обучением_и_поимённый() -> None:
    assert "training_enrollment" in ALL_SOURCES
    assert "training_enrollment" in ATTENTION_SOURCES
    assert discipline_of("training_enrollment") is Discipline.TRAINING
    assert "training_enrollment" in PERSON_SCOPED_SOURCES


def _program(tenant_id: str, title: str = "Охрана труда для рабочих") -> TrainingProgram:
    return TrainingProgram(
        tenant_id=tenant_id, code="ОТ-Р", title=title, category="ot", kind="program"
    )


def _enrollment(tenant_id: str, *, program_id, person_id, due_at, status="assigned", **extra):
    return TrainingEnrollment(
        tenant_id=tenant_id,
        training_program_id=program_id,
        person_id=person_id,
        status=status,
        due_at=due_at,
        **extra,
    )


class TestКалендарь:
    async def test_просроченное_и_будущее_видны_сданное_проваленное_удалённое_без_срока_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        person = await data_factory.create_person(
            tenant=tenant, session=test_db_session, first_name="Олег", last_name="Кузнецов"
        )
        program = _program(tid)
        test_db_session.add(program)
        await test_db_session.flush()
        test_db_session.add_all(
            [
                # Срок прошёл 5 дней назад, ещё не начато — просрочка.
                _enrollment(
                    tid, program_id=program.id, person_id=person.id, due_at=NOW - timedelta(days=5)
                ),
                # В процессе, срок через 10 дней — близкий срок.
                _enrollment(
                    tid,
                    program_id=program.id,
                    person_id=person.id,
                    due_at=NOW + timedelta(days=10),
                    status="in_progress",
                    progress_percent=40,
                ),
                # Сдано с прошедшим сроком — итог есть, срок не давит.
                _enrollment(
                    tid,
                    program_id=program.id,
                    person_id=person.id,
                    due_at=NOW - timedelta(days=20),
                    status="passed",
                ),
                # Провалено — тоже итог.
                _enrollment(
                    tid,
                    program_id=program.id,
                    person_id=person.id,
                    due_at=NOW - timedelta(days=20),
                    status="failed",
                ),
                # Удалено.
                _enrollment(
                    tid,
                    program_id=program.id,
                    person_id=person.id,
                    due_at=NOW - timedelta(days=20),
                    deleted_at=NOW - timedelta(days=1),
                ),
                # Без срока — не срок.
                _enrollment(tid, program_id=program.id, person_id=person.id, due_at=None),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(
            source_types=["training_enrollment"], include_sla=True, include_fact=True
        )

        assert response.total == 2
        assert response.overdue_count == 1
        overdue, soon = response.items
        assert overdue.title == "Назначение: Охрана труда для рабочих — Кузнецов Олег"
        assert overdue.status == "overdue"
        assert overdue.is_overdue is True
        assert overdue.sla_band == "overdue"
        assert overdue.person_id == str(person.id)
        assert overdue.extra["status"] == "assigned"
        assert overdue.extra["person_name"] == "Кузнецов Олег"
        assert soon.status == "in_progress"
        assert soon.is_overdue is False
        assert soon.extra["progress_percent"] == 40.0
        counts = {row.source_type: row for row in response.by_source}
        assert counts["training_enrollment"].count == 2
        assert counts["training_enrollment"].overdue_count == 1

    async def test_отбор_по_человеку_отдаёт_только_его_назначения(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        mine = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Свой",
            last_name="Сотрудник",
        )
        stranger = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Чужой",
            last_name="Сотрудник",
        )
        program = _program(tid)
        test_db_session.add(program)
        await test_db_session.flush()
        test_db_session.add_all(
            [
                _enrollment(
                    tid, program_id=program.id, person_id=mine.id, due_at=NOW - timedelta(days=2)
                ),
                _enrollment(
                    tid,
                    program_id=program.id,
                    person_id=stranger.id,
                    due_at=NOW - timedelta(days=2),
                ),
                _enrollment(
                    "someone-else",
                    program_id=program.id,
                    person_id=None,
                    due_at=NOW - timedelta(days=2),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        assert (await service.list_events(source_types=["training_enrollment"])).total == 2

        only_mine = await service.list_events(
            source_types=["training_enrollment"], person_id=str(mine.id)
        )
        assert only_mine.total == 1
        assert only_mine.overdue_count == 1
        assert [item.person_id for item in only_mine.items] == [str(mine.id)]


class TestЦентрВнимания:
    async def test_просроченное_назначение_доходит_до_центра_внимания_одной_цифрой_с_блокером(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Строка «Обучение», пункт ленты и блокер готовности — одно число."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            person = await data_factory.create_person(
                tenant=tenant, session=session, first_name="Анна", last_name="Смирнова"
            )
            program = _program(str(tenant.id), title="Работы на высоте")
            session.add(program)
            await session.flush()
            session.add_all(
                [
                    _enrollment(
                        str(tenant.id),
                        program_id=program.id,
                        person_id=person.id,
                        due_at=NOW - timedelta(days=3),
                    ),
                    _enrollment(
                        str(tenant.id),
                        program_id=program.id,
                        person_id=person.id,
                        due_at=NOW - timedelta(days=3),
                        status="passed",
                    ),
                ]
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get("/api/v1/workspace/attention", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        items = [item for item in body["items"] if item["item_type"] == "training_enrollment"]
        assert len(items) == 1, body["items"]
        assert items[0]["discipline"] == "training"
        assert items[0]["title"] == "Назначение: Работы на высоте — Смирнова Анна"
        training = next(row for row in body["disciplines"] if row["code"] == "training")
        assert training["overdue"] == 1
        blocker = next(b for b in body["blockers"] if b["code"] == "training_overdue")
        assert blocker["count"] == training["overdue"], "блокер и строка дисциплины — одна формула"
