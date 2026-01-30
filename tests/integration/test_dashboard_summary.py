from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.models import Incident, IncidentStage, IncidentStatus, IncidentType, RoleEnum, TrainingCourse, TrainingPlan
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.models.risk import RiskAssessment, RiskHazard


@pytest.mark.anyio
async def test_dashboard_summary_rolls_up_metrics(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)

        overdue_task = Task(
            tenant_id=tenant.id,
            title="Overdue",
            due_at=datetime.now(timezone.utc) - timedelta(days=1),
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
        )
        critical_task = Task(
            tenant_id=tenant.id,
            title="Critical",
            due_at=datetime.now(timezone.utc) + timedelta(days=3),
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.CRITICAL,
        )

        course = TrainingCourse(tenant_id=tenant.id, title="Safety Basics", code="SAFE-1")
        session.add(course)
        await session.flush()

        training_overdue = TrainingPlan(
            tenant_id=tenant.id,
            company_id=company.id,
            course_id=course.id,
            due_date=date.today() - timedelta(days=2),
        )
        training_due_soon = TrainingPlan(
            tenant_id=tenant.id,
            company_id=company.id,
            course_id=course.id,
            due_date=date.today() + timedelta(days=5),
        )

        incident = Incident(
            tenant_id=tenant.id,
            title="Incident",
            incident_type=IncidentType.ACCIDENT,
            occurred_at=datetime.now(timezone.utc),
            company_id=company.id,
            site_id=site.id,
            status=IncidentStatus.REPORTED,
            investigation_stage=IncidentStage.REGISTRATION,
        )

        hazard = RiskHazard(
            tenant_id=tenant.id,
            code="fall",
            title="Fall risk",
            module="ot",
            recommended_measures=[],
        )
        session.add(hazard)
        await session.flush()

        assessment = RiskAssessment(
            tenant_id=tenant.id,
            assessment_key="dash-assessment",
            assessment_version=1,
            hazard_id=hazard.id,
            severity_before=1,
            likelihood_before=1,
            score_before=1,
            band_before="low",
            severity_after=1,
            likelihood_after=1,
            score_after=1,
            band_after="low",
        )

        session.add_all(
            [
                overdue_task,
                critical_task,
                training_overdue,
                training_due_soon,
                incident,
                assessment,
            ]
        )
        await session.commit()

    response = await async_client.get("/api/v1/dashboard/summary", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["overdue_tasks"] == 1
    assert payload["critical_obligations"] == 1
    assert payload["incidents_open"] == 1
    assert payload["risks_total"] == 1
    assert payload["training"]["total"] == 2
    assert payload["training"]["overdue"] == 1
    assert payload["training"]["due_soon"] == 1
    assert payload["training"]["status"] == "critical"
    assert payload["generated_at"]
