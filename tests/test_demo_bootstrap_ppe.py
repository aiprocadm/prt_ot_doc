"""Demo bootstrap seeds PPE norms, sizes and issues covering all card statuses."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import Person, Position, PPEIssue, PPEItem, PPENorm
from app.services.demo_bootstrap import _seed_ppe_demo


@pytest.mark.asyncio
async def test_seed_ppe_demo_idempotent(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="Demo PPE Co")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Демо-должность")
        session.add(position)
        await session.commit()
        position_id = str(position.id)
    person = await data_factory.create_person(
        tenant=tenant, company=company, position_id=position_id
    )

    async with sessionmaker() as session:
        person_row = (
            await session.execute(select(Person).where(Person.id == person.id))
        ).scalar_one()
        await _seed_ppe_demo(session, str(tenant.id), person_row, position_id)
        await session.commit()

    async with sessionmaker() as session:
        norms = (
            (await session.execute(select(PPENorm).where(PPENorm.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        items = (
            (await session.execute(select(PPEItem).where(PPEItem.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        issues = (
            (await session.execute(select(PPEIssue).where(PPEIssue.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
        person_row = (
            await session.execute(select(Person).where(Person.id == person.id))
        ).scalar_one()
    assert len(norms) >= 3
    assert all(n.item_id for n in norms)
    assert len(items) >= 3
    assert len(issues) >= 2  # активная + просроченная
    assert person_row.ppe_sizes and person_row.ppe_sizes.get("height")

    # идемпотентность: второй прогон не плодит дублей
    async with sessionmaker() as session:
        person_row = (
            await session.execute(select(Person).where(Person.id == person.id))
        ).scalar_one()
        await _seed_ppe_demo(session, str(tenant.id), person_row, position_id)
        await session.commit()
    async with sessionmaker() as session:
        norms2 = (
            (await session.execute(select(PPENorm).where(PPENorm.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
    assert len(norms2) == len(norms)
