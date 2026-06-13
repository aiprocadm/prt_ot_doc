from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_register_and_named_list_endpoints(async_client, sessionmaker, data_factory, make_auth_headers):
    from app.models.models import MedicalFactor, Position, PositionHazardLink
    from app.models.risk import RiskHazard
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        hazard = RiskHazard(tenant_id=tenant.id, code="noise", title="Шум", medical_factor_code="4.4")
        session.add(hazard)
        await session.flush()
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
        session.add(pos)
        await session.flush()
        session.add(PositionHazardLink(tenant_id=tenant.id, position_id=pos.id, hazard_id=hazard.id))
        await data_factory.create_person(tenant=tenant, company=company, session=session,
                                         position_id=pos.id, first_name="Иван", last_name="Петров")
        session.add(MedicalFactor(tenant_id=tenant.id, code="4.4", name="Шум",
                                  exam_kinds=["periodic"], periodicity_months=12))
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    r1 = await async_client.get("/api/v1/medical/contingent/register", headers=headers)
    assert r1.status_code == status.HTTP_200_OK, r1.text
    reg = r1.json()["items"]
    assert any(row["headcount"] >= 1 and any(f["code"] == "4.4" for f in row["factors"]) for row in reg)

    r2 = await async_client.get("/api/v1/medical/named-list", headers=headers)
    assert r2.status_code == status.HTTP_200_OK, r2.text
    named = r2.json()["items"]
    assert any(any(f["code"] == "4.4" for f in row["factors"]) for row in named)
