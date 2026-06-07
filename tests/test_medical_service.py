from __future__ import annotations

from datetime import date

import pytest

from app.domains.medical import service as svc
from app.models.models import MedicalExamKind, MedicalFitness


@pytest.mark.asyncio
async def test_record_exam_unfit_opens_suspension_then_fit_lifts(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

        tid = str(tenant.id)
        exam1 = await svc.record_exam(
            session, tenant_id=tid, actor_id=None,
            person_id=person.id, exam_kind=MedicalExamKind.PERIODIC,
            exam_date=date(2026, 1, 1), fitness=MedicalFitness.UNFIT,
            contraindications=["asthma"], conclusion=None, restrictions=None,
            valid_until=None, medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        actives = await svc.list_active_suspensions(session, tenant_id=tid, person_ids=[person.id])
        assert len(actives) == 1
        assert actives[0].reason.value == "contraindication"
        assert exam1.valid_until == date(2027, 1, 1)  # default periodic interval 365

        await svc.record_exam(
            session, tenant_id=tid, actor_id=None,
            person_id=person.id, exam_kind=MedicalExamKind.PERIODIC,
            exam_date=date(2026, 2, 1), fitness=MedicalFitness.FIT,
            contraindications=[], conclusion=None, restrictions=None,
            valid_until=None, medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        actives = await svc.list_active_suspensions(session, tenant_id=tid, person_ids=[person.id])
        assert actives == []


@pytest.mark.asyncio
async def test_record_exam_unknown_person_raises(sessionmaker, data_factory):
    from app.models.models import MedicalExamKind
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await session.commit()
        with pytest.raises(ValueError):
            await svc.record_exam(
                session, tenant_id=str(tenant.id), actor_id=None,
                person_id="00000000-0000-0000-0000-000000000000",
                exam_kind=MedicalExamKind.PERIODIC, exam_date=date(2026, 1, 1),
                fitness=None, contraindications=[], conclusion=None, restrictions=None,
                valid_until=None, medical_org_name=None, referral_id=None, exam_type=None,
            )


@pytest.mark.asyncio
async def test_record_exam_respects_explicit_valid_until(sessionmaker, data_factory):
    from app.models.models import MedicalExamKind
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()
        exam = await svc.record_exam(
            session, tenant_id=str(tenant.id), actor_id=None, person_id=person.id,
            exam_kind=MedicalExamKind.PERIODIC, exam_date=date(2026, 1, 1), fitness=None,
            contraindications=[], conclusion=None, restrictions=None,
            valid_until=date(2026, 6, 1), medical_org_name=None, referral_id=None, exam_type=None,
        )
        await session.commit()
        assert exam.valid_until == date(2026, 6, 1)
