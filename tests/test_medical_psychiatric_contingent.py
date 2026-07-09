"""compute_contingent adds PSYCHIATRIC for positions mapped to a 695 activity."""

from datetime import date

import pytest

from app.domains.medical.service import compute_contingent
from app.models.models import (
    Position,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)


@pytest.mark.asyncio
async def test_contingent_includes_psychiatric_for_mapped_position(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Крановщик")
        session.add(pos)
        await session.flush()
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="height", name="Работы на высоте", interval_days=1825
            )
        )
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="height"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            position_id=pos.id, first_name="Иван", last_name="Петров",
        )
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 7, 9))

    assert any(
        it["person_id"] == person.id
        and it["exam_kind"] == "psychiatric"
        and it["status"] == "missing"
        for it in items
    )


@pytest.mark.asyncio
async def test_contingent_no_psychiatric_when_activity_not_in_catalog(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Бухгалтер")
        session.add(pos)
        await session.flush()
        # mapping references a code with NO catalog row → not subject
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="ghost"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session,
            position_id=pos.id, first_name="Пётр", last_name="Сидоров",
        )
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 7, 9))

    assert not any(
        it["person_id"] == person.id and it["exam_kind"] == "psychiatric" for it in items
    )
