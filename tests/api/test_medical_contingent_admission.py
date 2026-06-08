"""Task 7.2 — suspension block + norm-aware admission guard integration test."""
from __future__ import annotations

import pytest

from app.services.person_admission import enforce_person_admission


@pytest.mark.asyncio
async def test_active_suspension_blocks_admission(sessionmaker, data_factory):
    from datetime import date, datetime, timezone

    from app.models.models import MedicalExam, MedicalSuspension, MedicalSuspensionStatus

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session
        )
        session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=date(2026, 1, 1),
                valid_until=date(2999, 1, 1),
            )
        )
        session.add(
            MedicalSuspension(
                tenant_id=tenant.id,
                person_id=person.id,
                reason="unfit",
                started_at=datetime.now(timezone.utc),
                status=MedicalSuspensionStatus.ACTIVE,
            )
        )
        await session.commit()

        with pytest.raises(ValueError) as ei:
            await enforce_person_admission(
                session, tenant_scope=(str(tenant.id),), persons=[person]
            )
        assert "medical_suspension" in str(ei.value)


@pytest.mark.asyncio
async def test_norm_aware_blocks_when_required_exam_missing(sessionmaker, data_factory):
    from datetime import date
    from app.models.models import MedicalNorm, MedicalExamKind, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="NA-block")
        session.add(pos); await session.flush()
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id,
                                exam_kind=MedicalExamKind.PERIODIC, interval_days=365))
        await session.commit()
        with pytest.raises(ValueError) as ei:
            await enforce_person_admission(session, tenant_scope=(str(tenant.id),), persons=[person])
        assert "medical_exam" in str(ei.value)


@pytest.mark.asyncio
async def test_norm_aware_passes_medical_when_required_exam_present(sessionmaker, data_factory):
    from datetime import date
    from app.models.models import MedicalExam, MedicalNorm, MedicalExamKind, Position
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="NA-pass")
        session.add(pos); await session.flush()
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=session, position_id=pos.id)
        session.add(MedicalNorm(tenant_id=tenant.id, position_id=pos.id,
                                exam_kind=MedicalExamKind.PERIODIC, interval_days=365))
        session.add(MedicalExam(tenant_id=tenant.id, person_id=person.id, exam_type="periodic",
                                exam_kind=MedicalExamKind.PERIODIC, exam_date=date(2026, 1, 1),
                                valid_until=date(2999, 1, 1)))
        await session.commit()
        # person has no training/ppe so admission still raises, but NOT for medical_exam
        with pytest.raises(ValueError) as ei:
            await enforce_person_admission(session, tenant_scope=(str(tenant.id),), persons=[person])
        assert "medical_exam" not in str(ei.value)
