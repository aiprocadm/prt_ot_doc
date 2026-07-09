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
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos.id,
            first_name="Иван",
            last_name="Петров",
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
        # A catalog row exists (with a DIFFERENT code) so the early-return guard is
        # bypassed and the per-person exclusion loop actually runs.
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="height", name="Работы на высоте", interval_days=1825
            )
        )
        # mapping references a code with NO catalog row → not subject
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="ghost"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos.id,
            first_name="Пётр",
            last_name="Сидоров",
        )
        await session.commit()
        items = await compute_contingent(session, tenant_id=str(tenant.id), today=date(2026, 7, 9))

    assert not any(
        it["person_id"] == person.id and it["exam_kind"] == "psychiatric" for it in items
    )


@pytest.mark.asyncio
async def test_record_psychiatric_exam_uses_activity_interval_and_fields(
    sessionmaker, data_factory
):
    from datetime import date

    from app.domains.medical.service import record_exam
    from app.models.models import MedicalExamKind, MedicalFitness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Водитель")
        session.add(pos)
        await session.flush()
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="transport", name="Транспорт", interval_days=1095
            )
        )
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="transport"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos.id,
            first_name="Глеб",
            last_name="Смирнов",
        )
        await session.flush()
        exam = await record_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=None,
            person_id=person.id,
            exam_kind=MedicalExamKind.PSYCHIATRIC,
            exam_date=date(2026, 1, 1),
            fitness=MedicalFitness.FIT,
            contraindications=[],
            conclusion=None,
            restrictions=None,
            valid_until=None,  # derive from activity interval
            medical_org_name="ВК № 3",
            referral_id=None,
            exam_type=None,
            psychiatric_protocol_no="ПРО-42",
            psychiatric_activity_codes=["transport"],
        )
        await session.commit()

    # 1095-day interval from the activity, not the 1825 default
    # (2026-01-01 + 1095d = 2028-12-31; 2028 is a leap year, so this is one day
    # short of the naive "3 calendar years later" 2029-01-01.)
    assert exam.valid_until == date(2028, 12, 31)  # 2026-01-01 + 1095d
    assert exam.psychiatric_protocol_no == "ПРО-42"
    assert exam.psychiatric_activity_codes == ["transport"]


@pytest.mark.asyncio
async def test_unfit_psychiatric_exam_opens_suspension(sessionmaker, data_factory):
    from datetime import date

    from app.domains.medical.service import list_active_suspensions, record_exam
    from app.models.models import MedicalExamKind, MedicalFitness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            first_name="Анна",
            last_name="Кот",
        )
        await session.flush()
        await record_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=None,
            person_id=person.id,
            exam_kind=MedicalExamKind.PSYCHIATRIC,
            exam_date=date(2026, 1, 1),
            fitness=MedicalFitness.UNFIT,
            contraindications=["transport"],
            conclusion=None,
            restrictions=None,
            valid_until=None,
            medical_org_name=None,
            referral_id=None,
            exam_type=None,
        )
        await session.commit()
        actives = await list_active_suspensions(
            session, tenant_id=str(tenant.id), person_ids=[person.id]
        )
    assert len(actives) == 1  # UNFIT psychiatric verdict blocks допуск via existing machinery


@pytest.mark.asyncio
async def test_psychiatric_interval_derives_from_mapping_not_passed_codes(
    sessionmaker, data_factory
):
    from datetime import date

    from app.domains.medical.service import record_exam
    from app.models.models import MedicalExamKind, MedicalFitness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="Водитель")
        session.add(pos)
        await session.flush()
        # Position is mapped to "transport" (1095d). "height" (1825d) also exists in the
        # catalog but is NOT mapped to this position.
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="transport", name="Транспорт", interval_days=1095
            )
        )
        session.add(
            PsychiatricActivityType(
                tenant_id=tenant.id, code="height", name="Работы на высоте", interval_days=1825
            )
        )
        session.add(
            PsychiatricPositionActivity(
                tenant_id=tenant.id, position_id=pos.id, activity_code="transport"
            )
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=session,
            position_id=pos.id,
            first_name="Глеб",
            last_name="Смирнов",
        )
        await session.flush()
        exam = await record_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=None,
            person_id=person.id,
            exam_kind=MedicalExamKind.PSYCHIATRIC,
            exam_date=date(2026, 1, 1),
            fitness=MedicalFitness.FIT,
            contraindications=[],
            conclusion=None,
            restrictions=None,
            valid_until=None,  # derive from POSITION mapping, not the passed codes
            medical_org_name=None,
            referral_id=None,
            exam_type=None,
            # Passed codes deliberately point at the 1825d activity; the mapped 1095d wins.
            psychiatric_activity_codes=["height"],
        )
        await session.commit()

    # Periodicity comes from the position→activity mapping ("transport", 1095d),
    # NOT from the passed psychiatric_activity_codes (["height"], 1825d).
    # 2026-01-01 + 1095d = 2028-12-31 (leap-year-correct).
    assert exam.valid_until == date(2028, 12, 31)
    # The passed codes are still persisted verbatim on the record.
    assert exam.psychiatric_activity_codes == ["height"]
