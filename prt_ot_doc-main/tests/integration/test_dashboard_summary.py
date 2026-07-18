from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.document_core import (
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
)
from app.models.models import (
    Incident,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    RoleEnum,
    TrainingCourse,
    TrainingPlan,
)
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.models.risk import RiskAssessment, RiskHazard
from app.models.safety_ops import InspectionPrepGap, InspectionPrepPackage


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


@pytest.mark.anyio
async def test_dashboard_operational_snapshot_returns_real_task_document_and_readiness_data(
    async_client, sessionmaker, data_factory, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)

        open_task = Task(
            tenant_id=tenant.id,
            title="Подготовить пакет проверки",
            due_at=datetime.now(timezone.utc) + timedelta(days=2),
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH,
            entity_type="inspection_prep",
            entity_id="pkg-1",
        )

        template = Template(
            tenant_id=tenant.id,
            code="audit-brief",
            name="Пакет проверки",
            description="desc",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"123",
            payload_key="templates/audit-brief.docx",
            status=TemplateVersionStatus.ACTIVE,
        )
        session.add(version)
        await session.flush()

        run = PipelineRun(
            tenant_id=tenant.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.DONE,
            context={"scope": "dashboard"},
            idempotency_key="dash-op-1",
            result_metadata={},
        )

        package = InspectionPrepPackage(
            tenant_id=tenant.id,
            code="pkg-001",
            title="Ростехнадзор",
            status="draft",
        )
        session.add(package)
        await session.flush()

        gap = InspectionPrepGap(
            tenant_id=tenant.id,
            package_id=package.id,
            gap_type="missing_document",
            severity="critical",
            title="Нет акта учений",
            status="open",
        )

        session.add_all([open_task, run, gap])
        await session.commit()

    response = await async_client.get("/api/v1/dashboard/operational", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["tasks"][0]["title"] == "Подготовить пакет проверки"
    assert payload["documents"][0]["title"] == "Пакет проверки"
    assert payload["documents"][0]["route_label"] == "Готов"
    assert payload["readiness"]["packages_total"] == 1
    assert payload["readiness"]["open_gaps"] == 1
    assert payload["readiness"]["critical_gaps"] == 1
    assert payload["readiness"]["readiness_score"] < 100
