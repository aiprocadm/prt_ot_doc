from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.training import (
    assign_training_plan,
    issue_certificate,
    register_training_session,
    upcoming_certificate_expirations,
)
from app.models.models import TrainingCourse
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_training_plan_and_certificate_flow(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)

        course = TrainingCourse(
            tenant_id=tenant.id,
            title="Working at height",
            valid_period_days=10,
        )
        session.add(course)
        await session.flush()
        await session.refresh(course)

        plan = await assign_training_plan(
            session,
            tenant_id=tenant.id,
            company_id=company.id,
            course_id=course.id,
            person_id=person.id,
            due_date=date.today() + timedelta(days=7),
        )
        session_record = await register_training_session(
            session,
            tenant_id=tenant.id,
            person_id=person.id,
            course_id=course.id,
            plan_id=plan.id,
        )
        result = await issue_certificate(
            session,
            tenant_id=tenant.id,
            person_id=person.id,
            course_id=course.id,
            plan_id=plan.id,
            session_id=session_record.id,
            issued_at=date.today(),
            valid_until=date.today() + timedelta(days=5),
        )
        await session.commit()

        expiring = await upcoming_certificate_expirations(
            session, tenant_id=tenant.id, before=date.today() + timedelta(days=6)
        )

    assert plan.id is not None
    assert session_record.completed_at is not None
    assert result.certificate.id is not None
    assert any(cert.id == result.certificate.id for cert in expiring)
