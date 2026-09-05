"""disciplines.deadlines.tick (BIZ-54-57 срез-62): регистрация и обход арендаторов."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.master_data import Person
from app.models.models import Company, Outbox
from app.models.road_safety import Driver
from app.services.celery_app import celery_app
from app.tasks import _core  # noqa: F401  -- importing registers @celery_app.task decorators


def test_beat_schedule_registers_disciplines_deadlines_daily() -> None:
    schedule = celery_app.conf.beat_schedule
    entry = schedule["disciplines-deadlines-daily"]
    assert entry["task"] == "disciplines.deadlines.tick"
    assert 4 in entry["schedule"].hour
    assert 45 in entry["schedule"].minute


def test_disciplines_deadlines_tick_task_is_registered() -> None:
    assert "disciplines.deadlines.tick" in celery_app.tasks


@pytest.mark.asyncio
async def test_тик_обходит_арендатора_и_заводит_событие(sessionmaker, data_factory):
    from app.tasks._core import _disciplines_deadlines_tick

    tenant = await data_factory.ensure_tenant(slug="test")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        await data_factory.set_modules(session, tenant.id, ("road_safety",))
        company = Company(tenant_id=tid, name="ООО Тик")
        session.add(company)
        await session.flush()
        person = Person(tenant_id=tid, company_id=company.id, first_name="Тик", last_name="Тиков")
        session.add(person)
        await session.flush()
        session.add(
            Driver(
                tenant_id=tid,
                person_id=person.id,
                license_number="77 ТК 000001",
                categories=["B"],
                license_due=date.today() - timedelta(days=2),
                status="admitted",
            )
        )
        await session.commit()

    total = await _disciplines_deadlines_tick()
    assert total >= 1

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(Outbox).where(
                        Outbox.tenant_id == tid,
                        Outbox.event_type == "DisciplineDeadlineOverdue",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
