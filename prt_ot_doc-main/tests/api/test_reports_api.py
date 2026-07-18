from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status

from app.models.models import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Inspection,
    InspectionStatus,
    InspectionType,
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    Prescription,
    PrescriptionStatus,
    RoleEnum,
    TrainingCourse,
    TrainingPlan,
)
from app.models.risk import RiskAssessment, RiskAssessmentItem, RiskHazard
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_reports_kpi_endpoint(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)

        course = TrainingCourse(tenant_id=str(tenant.id), title="HSE", code="HSE-1")
        session.add(course)
        await session.flush()

        session.add(
            TrainingPlan(
                tenant_id=str(tenant.id),
                company_id=company.id,
                person_id=person.id,
                course_id=course.id,
                due_date=date.today() - timedelta(days=1),
            )
        )

        item = PPEItem(tenant_id=str(tenant.id), name="Helmet", code="H-01")
        session.add(item)
        await session.flush()
        session.add(
            PPEIssue(
                tenant_id=str(tenant.id),
                person_id=person.id,
                item_id=item.id,
                item_name="Helmet",
                quantity=1,
                status=PPEIssueStatus.ISSUED,
                issued_at=datetime.now(timezone.utc),
            )
        )

        incident = Incident(
            tenant_id=str(tenant.id),
            title="Slip",
            company_id=company.id,
            site_id=site.id,
            occurred_at=datetime.now(timezone.utc),
            incident_type=IncidentType.NEAR_MISS,
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.REPORTED,
        )
        session.add(incident)

        hazard = RiskHazard(
            tenant_id=str(tenant.id),
            code="HZ-1",
            title="Noise",
            module="ot",
            recommended_measures=[],
        )
        session.add(hazard)
        await session.flush()

        assessment = RiskAssessment(
            tenant_id=str(tenant.id),
            assessment_key="kpi",
            assessment_version=1,
            methodology_id=None,
            methodology_version=1,
            company_id=company.id,
            hazard_id=hazard.id,
            severity_before=4,
            likelihood_before=4,
            score_before=16,
            band_before="high",
            severity_after=4,
            likelihood_after=4,
            score_after=16,
            band_after="high",
        )
        session.add(assessment)
        await session.flush()
        session.add(
            RiskAssessmentItem(
                tenant_id=str(tenant.id),
                assessment_id=assessment.id,
                hazard_id=hazard.id,
                probability=4,
                severity=4,
                score=16,
                level="high",
                methodology_version=1,
            )
        )

        inspection = Inspection(
            tenant_id=str(tenant.id),
            company_id=company.id,
            site_id=site.id,
            authority="Rostekhnadzor",
            inspection_type=InspectionType.INTERNAL,
            status=InspectionStatus.IN_PROGRESS,
        )
        session.add(inspection)
        await session.flush()

        session.add(
            Prescription(
                tenant_id=str(tenant.id),
                inspection_id=inspection.id,
                description="Fix guard",
                due_at=date.today() - timedelta(days=2),
                status=PrescriptionStatus.OPEN,
            )
        )

        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/reports/kpi", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["risks_high"] >= 1
    assert payload["trainings_overdue"] >= 1
    assert payload["ppe_issues_month"] >= 1
    assert payload["incidents_open"] >= 1
    assert payload["prescriptions_overdue"] >= 1
