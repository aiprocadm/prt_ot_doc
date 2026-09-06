"""Regression for the person-compliance projection (review sweep #16).

rebuild_person_projection used to hardcode readiness_status='unknown' and never
populate overdue_trainings/overdue_briefings. It now derives them (a lapsed
training-cert expiry / briefing valid_until = overdue) and sets readiness to
'ready' or 'blocked'.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.projections.models import PersonComplianceReadModel
from app.modules.projections.services import ProjectionOrchestrator
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_person_compliance_projection_sets_readiness_ready(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()
        tenant_id = str(tenant.id)
        person_id = person.id
        await ProjectionOrchestrator(session, tenant_id).rebuild_person_projection()

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(PersonComplianceReadModel).where(
                    PersonComplianceReadModel.tenant_id == tenant_id,
                    PersonComplianceReadModel.person_id == person_id,
                )
            )
        ).scalar_one()
        # No overdue items -> ready (was hardcoded "unknown").
        assert row.readiness_status == "ready"
        assert row.overdue_trainings == 0
        assert row.overdue_briefings == 0


@pytest.mark.asyncio
async def test_проекция_уволенного_не_считает_и_убирает_его_строку(
    sessionmaker, data_factory: TestDataFactory
):
    """«Уволенный не в счёт» (BIZ-54-57 срез-97): проекцию читают только сводные
    цифры аналитики. Трое с истёкшим удостоверением: работающий — «blocked»;
    уволенный и удалённый строки не получают, а старая строка уволенного после
    пересборки исчезает — вместе с ней и `overdue_compliance_items`."""
    from datetime import datetime, timedelta, timezone

    from app.models.master_data import EmploymentStatus, Person
    from app.models.models import TrainingEnrollment, TrainingProgram
    from app.modules.analytics.services import AnalyticsAggregationService, DashboardFilters

    now = datetime.now(tz=timezone.utc)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        here = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Работает", session=session
        )
        gone = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Уволится", session=session
        )
        erased = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Удалён", session=session, deleted_at=now
        )
        program = TrainingProgram(
            tenant_id=tenant.id, code="ОТ-97", title="Охрана труда", category="ot", kind="program"
        )
        session.add(program)
        await session.flush()
        session.add_all(
            [
                TrainingEnrollment(
                    tenant_id=tenant.id,
                    training_program_id=program.id,
                    person_id=person.id,
                    status="completed",
                    expires_at=now - timedelta(days=30),
                )
                for person in (here, gone, erased)
            ]
        )
        await session.commit()
        tenant_id = str(tenant.id)
        # Первая пересборка — «gone» ещё работает и получает строку «blocked».
        await ProjectionOrchestrator(session, tenant_id).rebuild_person_projection()
        rows = {
            row.person_id: row.readiness_status
            for row in (
                await session.execute(
                    select(PersonComplianceReadModel).where(
                        PersonComplianceReadModel.tenant_id == tenant_id
                    )
                )
            ).scalars()
        }
        assert rows == {here.id: "blocked", gone.id: "blocked"}
        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters()
        )
        assert counters["overdue_compliance_items"] == 2

        # Уволили — после пересборки его строки нет, и сводка это видит.
        person = await session.get(Person, gone.id)
        person.employment_status = EmploymentStatus.TERMINATED
        await session.commit()
        await ProjectionOrchestrator(session, tenant_id).rebuild_person_projection()
        rows = {
            row.person_id: row.readiness_status
            for row in (
                await session.execute(
                    select(PersonComplianceReadModel).where(
                        PersonComplianceReadModel.tenant_id == tenant_id
                    )
                )
            ).scalars()
        }
        assert rows == {here.id: "blocked"}
        counters = await AnalyticsAggregationService(session, tenant_id).base_counters(
            DashboardFilters()
        )
        assert counters["overdue_compliance_items"] == 1
