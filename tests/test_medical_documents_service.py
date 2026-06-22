"""Document builders: контингент (position-level) + поименный список (person-level)."""

from datetime import date

import pytest

from app.domains.medical.service import build_contingent_register, build_named_list
from app.models.models import MedicalFactor, Position, PositionHazardLink
from app.models.risk import RiskHazard


async def _seed(session, data_factory):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session)
    hazard = RiskHazard(tenant_id=tenant.id, code="noise", title="Шум", medical_factor_code="4.4")
    session.add(hazard)
    await session.flush()
    pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
    session.add(pos)
    await session.flush()
    session.add(PositionHazardLink(tenant_id=tenant.id, position_id=pos.id, hazard_id=hazard.id))
    await data_factory.create_person(
        tenant=tenant,
        company=company,
        session=session,
        position_id=pos.id,
        first_name="Иван",
        last_name="Петров",
    )
    session.add(
        MedicalFactor(
            tenant_id=tenant.id,
            code="4.4",
            name="Шум",
            exam_kinds=["periodic"],
            periodicity_months=12,
        )
    )
    await session.commit()
    return str(tenant.id), pos.id


@pytest.mark.asyncio
async def test_contingent_register_groups_by_position_with_headcount(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, pos_id = await _seed(session, data_factory)
        rows = await build_contingent_register(
            session, tenant_id=tenant_id, today=date(2026, 6, 13)
        )
    assert len(rows) == 1
    row = rows[0]
    assert row["position_id"] == pos_id
    assert row["headcount"] == 1
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert "periodic" in row["exam_kinds"]


@pytest.mark.asyncio
async def test_named_list_lists_person_with_factors_and_status(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant_id, _pos = await _seed(session, data_factory)
        rows = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert len(rows) == 1
    row = rows[0]
    assert row["full_name"] == "Петров Иван"
    assert row["position_name"] == "Сварщик"
    assert {"code": "4.4", "name": "Шум"} in row["factors"]
    assert row["status"] == "missing"
    assert row["next_due_date"] == date(2026, 6, 13)


@pytest.mark.asyncio
async def test_documents_empty_without_factor_mapping(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = str(tenant.id)
        reg = await build_contingent_register(session, tenant_id=tenant_id, today=date(2026, 6, 13))
        named = await build_named_list(session, tenant_id=tenant_id, today=date(2026, 6, 13))
    assert reg == [] and named == []
