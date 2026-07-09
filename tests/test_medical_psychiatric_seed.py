"""seed_default_activity_types is idempotent and loads the standard 695 set."""

import pytest
from sqlalchemy import func, select

from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS
from app.domains.medical.service import seed_default_activity_types
from app.models.models import PsychiatricActivityType


@pytest.mark.asyncio
async def test_seed_defaults_idempotent(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        n1 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        n2 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        total = await session.scalar(
            select(func.count())
            .select_from(PsychiatricActivityType)
            .where(PsychiatricActivityType.tenant_id == tenant.id)
        )
    assert n1 == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)
    assert n2 == 0  # second run inserts nothing
    assert int(total) == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)


@pytest.mark.asyncio
async def test_demo_seed_maps_position_to_activity(sessionmaker, data_factory):
    from app.models.models import Position, PsychiatricPositionActivity
    from app.services.demo_bootstrap import _seed_psychiatric_activities_demo

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Демо-должность")
        session.add(pos)
        await session.flush()
        await _seed_psychiatric_activities_demo(session, str(tenant.id), str(pos.id))
        await session.commit()
        rows = (
            await session.execute(
                select(PsychiatricPositionActivity.activity_code).where(
                    PsychiatricPositionActivity.tenant_id == tenant.id,
                    PsychiatricPositionActivity.position_id == pos.id,
                )
            )
        ).all()
    assert ("height",) in rows
