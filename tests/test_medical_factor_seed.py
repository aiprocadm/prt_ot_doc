"""§9.2 demo seed: the named list is non-empty factor-driven after seeding."""

from datetime import date

import pytest

from app.domains.medical.service import build_named_list
from app.models.models import Position
from app.services.demo_bootstrap import _seed_medical_factor_demo


@pytest.mark.asyncio
async def test_seed_medical_factor_demo_populates_named_list(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Мастер участка")
        session.add(pos)
        await session.flush()
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos.id,
            first_name="Иван",
            last_name="Петров",
        )
        await _seed_medical_factor_demo(session, str(tenant.id), str(pos.id))
        await session.commit()
        rows = await build_named_list(session, tenant_id=str(tenant.id), today=date(2026, 6, 13))
    assert any(any(f["code"] == "4.4" for f in row["factors"]) for row in rows)
