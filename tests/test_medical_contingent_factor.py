"""compute_contingent must include factor-driven persons with NO manual norm."""
from datetime import date

import pytest

from app.domains.medical.service import compute_contingent
from app.models.models import MedicalFactor, Position, PositionHazardLink
from app.models.risk import RiskHazard


@pytest.mark.asyncio
async def test_contingent_includes_factor_driven_person_without_norm(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        hazard = RiskHazard(tenant_id=tenant.id, code="noise", title="Шум",
                            medical_factor_code="4.4")
        session.add(hazard)
        await session.flush()
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
        session.add(pos)
        await session.flush()
        session.add(PositionHazardLink(
            tenant_id=tenant.id, position_id=pos.id, hazard_id=hazard.id,
        ))
        await session.flush()
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id,
            first_name="Иван", last_name="Петров",
        )
        session.add(MedicalFactor(tenant_id=tenant.id, code="4.4", name="Шум",
                                  exam_kinds=["periodic"], periodicity_months=12))
        await session.commit()

        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 6, 13))

    # No MedicalNorm created — the person enters the contingent factor-driven.
    assert any(it["person_id"] == person.id and it["exam_kind"] == "periodic"
               and it["status"] == "missing" for it in items)


@pytest.mark.asyncio
async def test_unknown_exam_kind_label_is_skipped_not_crashing(sessionmaker, data_factory):
    from datetime import date
    from app.domains.medical.service import compute_contingent
    from app.models.models import MedicalFactor, Position, PositionHazardLink
    from app.models.risk import RiskHazard
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        hazard = RiskHazard(tenant_id=tenant.id, code="noise2", title="Шум2",
                            medical_factor_code="4.5")
        session.add(hazard)
        await session.flush()
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик2")
        session.add(pos)
        await session.flush()
        session.add(PositionHazardLink(
            tenant_id=tenant.id, position_id=pos.id, hazard_id=hazard.id,
        ))
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id,
            first_name="Иван", last_name="Петров",
        )
        # one bogus label + one valid label
        session.add(MedicalFactor(tenant_id=tenant.id, code="4.5", name="Шум2",
                                  exam_kinds=["bogus_kind", "periodic"], periodicity_months=12))
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 6, 13))
    kinds = {it["exam_kind"] for it in items if it["person_id"] == person.id}
    assert "periodic" in kinds and "bogus_kind" not in kinds
