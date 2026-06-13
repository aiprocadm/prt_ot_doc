"""§6.9 Срез-3 demo seed: a briefing template opted into code-flow signing exists (idempotent)."""
import pytest
from sqlalchemy import select

from app.models.models import BriefingTemplate
from app.services.demo_bootstrap import _seed_briefing_code_flow_demo


@pytest.mark.asyncio
async def test_seed_briefing_code_flow_demo(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        # idempotent: calling twice must not duplicate
        await _seed_briefing_code_flow_demo(session, str(tenant.id), person)
        await _seed_briefing_code_flow_demo(session, str(tenant.id), person)
        await session.commit()

        flagged = (await session.execute(select(BriefingTemplate).where(
            BriefingTemplate.tenant_id == tenant.id,
            BriefingTemplate.require_signature_code.is_(True),
        ))).scalars().all()
        assert len(flagged) >= 1

        only_one = (await session.execute(select(BriefingTemplate).where(
            BriefingTemplate.tenant_id == tenant.id,
            BriefingTemplate.code == "demo-primary-code",
        ))).scalars().all()
        assert len(only_one) == 1
