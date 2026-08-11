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
