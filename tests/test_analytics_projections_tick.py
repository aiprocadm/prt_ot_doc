"""analytics.projections.tick (BIZ-54-57 срез-97): ночная пересборка read
model'ов аналитики по всем активным арендаторам и её место в расписании."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.projections.models import PersonComplianceReadModel
from app.services.celery_app import celery_app


def test_beat_schedule_registers_analytics_projections_daily() -> None:
    schedule = celery_app.conf.beat_schedule
    entry = schedule["analytics-projections-daily"]
    assert entry["task"] == "analytics.projections.tick"
    assert "analytics.projections.tick" in celery_app.tasks


@pytest.mark.asyncio
async def test_analytics_projections_tick_rebuilds_person_compliance(sessionmaker, data_factory):
    from app.tasks._core import _analytics_projections_tick

    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant, last_name="Проекция")

    total = await _analytics_projections_tick()
    assert total >= 1

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(PersonComplianceReadModel).where(
                    PersonComplianceReadModel.tenant_id == str(tenant.id),
                    PersonComplianceReadModel.person_id == person.id,
                )
            )
        ).scalar_one()
    assert row.readiness_status == "ready"


@pytest.mark.asyncio
async def test_проекция_площадок_считает_работающих_через_рабочее_место(sessionmaker, data_factory):
    """До среза-97 пересборка падала на `Person.site_id` (ARCH-2). Теперь люди
    площадки — через рабочее место, и только работающие («уволенный не в счёт»)."""
    from app.models.master_data import EmploymentStatus, Workplace
    from app.modules.projections.models import SiteSafetyReadModel
    from app.modules.projections.services import SiteSafetyProjectionService

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        workplace = Workplace(
            tenant_id=tenant.id, company_id=company.id, site_id=site.id, name="Пост-97"
        )
        session.add(workplace)
        await session.flush()
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Работает",
            session=session,
            workplace_id=workplace.id,
        )
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Уволен",
            session=session,
            workplace_id=workplace.id,
            employment_status=EmploymentStatus.TERMINATED,
        )
        await data_factory.create_person(
            tenant=tenant, company=company, last_name="Без места", session=session
        )
        await session.commit()
        tenant_id = str(tenant.id)
        total = await SiteSafetyProjectionService(session, tenant_id).rebuild()
        assert total == 1
        row = (
            await session.execute(
                select(SiteSafetyReadModel).where(
                    SiteSafetyReadModel.tenant_id == tenant_id,
                    SiteSafetyReadModel.site_id == site.id,
                )
            )
        ).scalar_one()
    assert row.active_people_count == 1
    assert row.readiness_status == "ready"
