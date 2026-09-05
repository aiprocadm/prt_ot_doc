"""Разд. 57.2: срок удостоверения по обучению — событие календаря и Центра внимания (срез-75).

До среза ``TrainingCertificate.valid_until`` жил только в ручке
``GET /training/certificates/expiring`` (фронт её не зовёт) и в карточке
сотрудника. В календаре, в Центре внимания и в разрезе по дисциплинам истёкшее
удостоверение не появлялось вовсе — специалист узнавал о нём с проверки.
Единственный обходной путь — ручной ``POST /compliance/recompute``, который
складывает снимок в неразмеченный источник ``compliance_deadline`` и в ленту
внимания не попадает.

Теперь это поимённый источник ``training_certificate`` дисциплины «Обучение»:
активное удостоверение с прошедшим ``valid_until`` — просрочка, с будущим —
близкий срок; отозванные, удалённые и бессрочные (``valid_until IS NULL``)
событиями не считаются.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.disciplines import (
    ATTENTION_SOURCES,
    PERSON_SCOPED_SOURCES,
    Discipline,
    discipline_of,
)
from app.models.models import RoleEnum, TrainingCertificate, TrainingCourse, TrainingProgram
from app.services.calendar_aggregator import ALL_SOURCES, CalendarAggregatorService
from tests.utils.factories import TestDataFactory

pytestmark = pytest.mark.anyio


def _program(tenant_id: str, title: str = "Охрана труда для руководителей") -> TrainingProgram:
    return TrainingProgram(
        tenant_id=tenant_id, code="ОТ-1", title=title, category="ot", kind="program"
    )


class TestКонтрактИсточника:
    def test_источник_объявлен_размечен_обучением_и_поимённый(self) -> None:
        assert "training_certificate" in ALL_SOURCES
        assert "training_certificate" in ATTENTION_SOURCES
        assert discipline_of("training_certificate") is Discipline.TRAINING
        assert (
            "training_certificate" in PERSON_SCOPED_SOURCES
        ), "рабочий должен видеть только своё удостоверение"


class TestКалендарь:
    async def test_истёкшее_и_действующее_видны_отозванное_удалённое_бессрочное_нет(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        tid = str(tenant.id)
        person = await data_factory.create_person(
            tenant=tenant, session=test_db_session, first_name="Пётр", last_name="Петров"
        )
        program = _program(tid)
        course = TrainingCourse(tenant_id=tid, title="Промбезопасность", duration_hours=16)
        test_db_session.add_all([program, course])
        await test_db_session.flush()
        today = date.today()
        test_db_session.add_all(
            [
                # Истекло 10 дней назад — просрочка, название из программы.
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-001",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=today - timedelta(days=375),
                    valid_until=today - timedelta(days=10),
                ),
                # Истекает через 20 дней — близкий срок, название из legacy-курса.
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-002",
                    course_id=course.id,
                    person_id=person.id,
                    issued_at=today - timedelta(days=345),
                    valid_until=today + timedelta(days=20),
                ),
                # Отозванное с прошедшим сроком — не событие.
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-003",
                    training_program_id=program.id,
                    person_id=person.id,
                    status="revoked",
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=30),
                ),
                # Удалённое — не событие.
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-004",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=30),
                    deleted_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
                # Бессрочное — срока нет, в календаре ему нечего делать.
                TrainingCertificate(
                    tenant_id=tid,
                    number="УД-005",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=today - timedelta(days=400),
                    valid_until=None,
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        response = await service.list_events(
            source_types=["training_certificate"], include_sla=True, include_fact=True
        )

        assert response.total == 2
        assert response.overdue_count == 1
        titles = [item.title for item in response.items]
        assert titles == [
            "Удостоверение: Охрана труда для руководителей — Петров Пётр",
            "Удостоверение: Промбезопасность — Петров Пётр",
        ]
        expired, valid = response.items
        assert expired.id.startswith("training_certificate:")
        assert expired.status == "expired"
        assert expired.is_overdue is True
        assert expired.sla_band == "overdue"
        assert expired.person_id == str(person.id)
        assert expired.extra["number"] == "УД-001"
        assert expired.extra["program_title"] == "Охрана труда для руководителей"
        assert expired.extra["person_name"] == "Петров Пётр", "имя — для задачи правила (срез-76)"
        assert expired.actual_at is not None, "факт — дата выдачи"
        assert valid.status == "valid"
        assert valid.is_overdue is False
        assert valid.sla_band != "overdue"
        assert valid.extra["course_title"] == "Промбезопасность"
        counts = {row.source_type: row for row in response.by_source}
        assert counts["training_certificate"].count == 2
        assert counts["training_certificate"].overdue_count == 1

    async def test_отбор_по_человеку_отдаёт_только_его_удостоверения(
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
        today = date.today()
        test_db_session.add_all(
            [
                TrainingCertificate(
                    tenant_id=tid,
                    number="СВ-1",
                    training_program_id=program.id,
                    person_id=mine.id,
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=3),
                ),
                TrainingCertificate(
                    tenant_id=tid,
                    number="ЧУ-1",
                    training_program_id=program.id,
                    person_id=stranger.id,
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=3),
                ),
                # Чужой арендатор — не видно даже без отбора по человеку.
                TrainingCertificate(
                    tenant_id="someone-else",
                    number="ЧА-1",
                    person_id=None,
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=3),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=tid, db=test_db_session)
        everyone = await service.list_events(source_types=["training_certificate"])
        assert everyone.total == 2

        only_mine = await service.list_events(
            source_types=["training_certificate"], person_id=str(mine.id)
        )
        assert only_mine.total == 1
        assert only_mine.overdue_count == 1
        assert [item.extra["number"] for item in only_mine.items] == ["СВ-1"]
        counts = {row.source_type: row for row in only_mine.by_source}
        assert counts["training_certificate"].count == 1
        assert counts["training_certificate"].overdue_count == 1


class TestЦентрВнимания:
    async def test_истёкшее_удостоверение_доходит_до_центра_внимания(
        self, async_client, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        """Строка «Обучение» и пункт ленты — без ручного recompute."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            person = await data_factory.create_person(
                tenant=tenant, session=session, first_name="Анна", last_name="Смирнова"
            )
            program = _program(str(tenant.id), title="Работы на высоте")
            session.add(program)
            await session.flush()
            session.add(
                TrainingCertificate(
                    tenant_id=str(tenant.id),
                    number="ВЫС-7",
                    training_program_id=program.id,
                    person_id=person.id,
                    issued_at=date.today() - timedelta(days=370),
                    valid_until=date.today() - timedelta(days=5),
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get("/api/v1/workspace/attention", headers=headers)

        assert response.status_code == 200, response.text
        body = response.json()
        items = [item for item in body["items"] if item["item_type"] == "training_certificate"]
        assert len(items) == 1, body["items"]
        assert items[0]["discipline"] == "training"
        assert items[0]["title"] == "Удостоверение: Работы на высоте — Смирнова Анна"
        assert items[0]["severity"] in {"critical", "high"}
        training = next(row for row in body["disciplines"] if row["code"] == "training")
        assert training["overdue"] >= 1
