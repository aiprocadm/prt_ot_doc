"""Tests for the Unified Employee Card aggregate (vNext-EMP-01 / Phase 3.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentStatus
from app.models.file import File, FileKind
from app.models.models import (
    AuditLog,
    BriefingEntry,
    BriefingJournal,
    BriefingTemplate,
    ComplianceDeadline,
    EmploymentStatus,
    Incident,
    IncidentPerson,
    IncidentPersonRole,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    MedicalExam,
    Permit,
    PermitStatus,
    Position,
    PPEIssue,
    PPEIssueStatus,
    RoleEnum,
    Training,
    TrainingStatus,
    Workplace,
)
from app.services.employee_card import EmployeeCardService
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _emp_headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


@pytest.mark.anyio
class TestEmployeeCardService:
    """Service-level tests for `EmployeeCardService.build`."""

    async def test_returns_none_for_unknown_person(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = EmployeeCardService(tenant_id=str(tenant.id), db=test_db_session)
        card = await service.build("00000000-0000-0000-0000-000000000000")
        assert card is None

    async def test_isolates_other_tenants(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(slug="emp-tenant-a", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="emp-tenant-b", session=test_db_session)
        company_a = await data_factory.create_company(tenant=tenant_a, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant_a, company=company_a, session=test_db_session,
            first_name="Cross", last_name="Tenant", email="cross-tenant@example.com",
        )

        service_other = EmployeeCardService(tenant_id=str(tenant_b.id), db=test_db_session)
        assert (await service_other.build(person.id)) is None

        service_owner = EmployeeCardService(tenant_id=str(tenant_a.id), db=test_db_session)
        card = await service_owner.build(person.id)
        assert card is not None
        assert card.person_id == person.id
        assert card.tenant_id == str(tenant_a.id)

    async def test_aggregates_full_lifecycle(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=test_db_session
        )
        position = Position(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Welder",
        )
        workplace = Workplace(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Shop floor 1",
        )
        test_db_session.add_all([position, workplace])
        await test_db_session.commit()
        await test_db_session.refresh(position)
        await test_db_session.refresh(workplace)

        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Иван",
            last_name="Петров",
            middle_name="Сергеевич",
            email="ivan.petrov@example.com",
            phone="+79991234567",
            employment_status=EmploymentStatus.ACTIVE,
            personnel_number="P-001",
            position_id=position.id,
            workplace_id=workplace.id,
        )

        # Linked user account (same tenant + email).
        await data_factory.create_user(
            tenant=tenant,
            email="ivan.petrov@example.com",
            role=RoleEnum.HR,
            session=test_db_session,
        )

        # Medical exam — one expired, one current.
        today = date.today()
        expired_exam = MedicalExam(
            tenant_id=tenant.id,
            person_id=person.id,
            exam_type="periodic",
            exam_date=today - timedelta(days=400),
            valid_until=today - timedelta(days=30),
            conclusion="fit",
        )
        current_exam = MedicalExam(
            tenant_id=tenant.id,
            person_id=person.id,
            exam_type="periodic",
            exam_date=today - timedelta(days=10),
            valid_until=today + timedelta(days=355),
            conclusion="fit",
        )
        test_db_session.add_all([expired_exam, current_exam])

        # PPE issues — one active, one expired, one returned.
        now = datetime.now(timezone.utc)
        ppe_active = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Hard hat",
            quantity=1,
            issued_at=now - timedelta(days=10),
            expires_at=now + timedelta(days=355),
            status=PPEIssueStatus.ISSUED,
        )
        ppe_expired = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Goggles",
            quantity=1,
            issued_at=now - timedelta(days=400),
            expires_at=now - timedelta(days=30),
            status=PPEIssueStatus.ISSUED,
        )
        ppe_returned = PPEIssue(
            tenant_id=tenant.id,
            person_id=person.id,
            item_name="Gloves",
            quantity=2,
            issued_at=now - timedelta(days=200),
            returned_at=now - timedelta(days=10),
            status=PPEIssueStatus.RETURNED,
        )
        test_db_session.add_all([ppe_active, ppe_expired, ppe_returned])

        # Permits — one active, one expired (still status=ACTIVE → flagged).
        permit_active = Permit(
            tenant_id=tenant.id,
            person_id=person.id,
            permit_type="height_works",
            issued_at=today - timedelta(days=10),
            valid_until=today + timedelta(days=20),
            status=PermitStatus.ACTIVE,
        )
        permit_expired = Permit(
            tenant_id=tenant.id,
            person_id=person.id,
            permit_type="electrical_4kv",
            issued_at=today - timedelta(days=400),
            valid_until=today - timedelta(days=30),
            status=PermitStatus.ACTIVE,
        )
        test_db_session.add_all([permit_active, permit_expired])

        # Legacy training row.
        legacy_training = Training(
            tenant_id=tenant.id,
            person_id=person.id,
            course_name="Initial briefing",
            status=TrainingStatus.COMPLETED,
            completed_at=now - timedelta(days=20),
        )
        test_db_session.add(legacy_training)

        # Incident with the person as a victim.
        incident = Incident(
            tenant_id=tenant.id,
            company_id=company.id,
            site_id=site.id,
            title="Slip on the floor",
            incident_type=IncidentType.MICROTRAUMA,
            severity=IncidentSeverity.LOW,
            status=IncidentStatus.INVESTIGATING,
            occurred_at=now - timedelta(days=5),
        )
        test_db_session.add(incident)
        await test_db_session.flush()
        link = IncidentPerson(
            tenant_id=tenant.id,
            incident_id=incident.id,
            person_id=person.id,
            role=IncidentPersonRole.VICTIM,
        )
        test_db_session.add(link)

        # Audit trail entry referencing the person.
        audit_entry = AuditLog(
            tenant_id=tenant.id,
            actor_email="hr-admin@example.com",
            action="update",
            object_type="person",
            object_id=str(person.id),
            ip="127.0.0.1",
            correlation_id="corr-emp-test",
            changed_fields={"phone": ["+79990000000", "+79991234567"]},
        )
        test_db_session.add(audit_entry)

        await test_db_session.commit()

        service = EmployeeCardService(tenant_id=str(tenant.id), db=test_db_session)
        card = await service.build(person.id)
        assert card is not None

        assert card.person_id == person.id
        assert card.personal.fio.startswith("Петров Иван")
        assert card.personal.position_name == "Welder"
        assert card.personal.workplace_name == "Shop floor 1"
        assert card.personal.employment_status == EmploymentStatus.ACTIVE

        assert card.roles_and_assignments.user_account is not None
        assert card.roles_and_assignments.user_account.role.lower() == "hr"

        assert card.training.sessions_count >= 1
        assert any(item.course_title == "Initial briefing" for item in card.training.sessions)

        assert card.medicals.count == 2
        assert card.medicals.expired_count == 1

        assert card.ppe.count == 3
        assert card.ppe.active_count == 2  # active + expired-but-issued
        assert card.ppe.expired_count == 1
        assert any(item.is_expired for item in card.ppe.items)

        assert card.permits.count == 2
        assert card.permits.expired_count == 1

        assert card.incidents.count == 1
        assert card.incidents.items[0].role == IncidentPersonRole.VICTIM
        assert card.incidents.items[0].id == incident.id

        assert card.audit.count == 1
        assert card.audit.items[0].action == "update"
        assert card.audit.items[0].correlation_id == "corr-emp-test"

    async def test_aggregates_documents_briefings_and_deadlines(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        """vNext-EMP-01 follow-up: card surfaces Documents/Briefings/Deadlines."""
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Doc",
            last_name="Holder",
            email="doc-holder@example.com",
        )

        # File row used as a real signed-file FK target (avoids relying on
        # SQLite's lax FK enforcement).
        signed_file = File(
            tenant_id=tenant.id,
            storage_key="test/signed.pdf",
            bucket="signed",
            sha256="0" * 64,
            size=1,
            mime="application/pdf",
            kind=FileKind.DOCUMENT,
        )
        test_db_session.add(signed_file)
        await test_db_session.flush()

        signed_doc, _ = await data_factory.create_document(
            tenant=tenant,
            company=company,
            person=person,
            status=DocumentStatus.SIGNED,
            session=test_db_session,
            signed_file_id=signed_file.id,
        )
        await data_factory.create_document(
            tenant=tenant,
            company=company,
            person=person,
            status=DocumentStatus.DRAFT,
            session=test_db_session,
        )
        # Reference the var so linters don't flag it as unused.
        assert signed_doc.signed_file_id == signed_file.id

        # Briefing template + journal + two entries (one current, one expired).
        now = datetime.now(timezone.utc)
        briefing_template = BriefingTemplate(
            tenant_id=tenant.id,
            code="bt-primary",
            title="Первичный инструктаж",
            briefing_type="primary",
        )
        journal = BriefingJournal(
            tenant_id=tenant.id,
            code="bj-primary",
            title="Журнал первичных",
            journal_type="primary",
        )
        test_db_session.add_all([briefing_template, journal])
        await test_db_session.flush()

        briefing_current = BriefingEntry(
            tenant_id=tenant.id,
            briefing_journal_id=journal.id,
            briefing_template_id=briefing_template.id,
            person_id=person.id,
            briefing_type="primary",
            briefing_date=now - timedelta(days=10),
            valid_until=now + timedelta(days=355),
            status="signed",
        )
        briefing_expired = BriefingEntry(
            tenant_id=tenant.id,
            briefing_journal_id=journal.id,
            briefing_template_id=briefing_template.id,
            person_id=person.id,
            briefing_type="primary",
            briefing_date=now - timedelta(days=400),
            valid_until=now - timedelta(days=30),
            status="signed",
        )
        test_db_session.add_all([briefing_current, briefing_expired])

        # Compliance deadlines — overdue, upcoming, closed.
        deadline_overdue = ComplianceDeadline(
            tenant_id=tenant.id,
            entity_type="medical_exam",
            entity_id="medical-1",
            person_id=person.id,
            due_at=now - timedelta(days=5),
            status="upcoming",
        )
        deadline_upcoming = ComplianceDeadline(
            tenant_id=tenant.id,
            entity_type="training_session",
            entity_id="training-1",
            person_id=person.id,
            due_at=now + timedelta(days=15),
            status="upcoming",
        )
        deadline_closed = ComplianceDeadline(
            tenant_id=tenant.id,
            entity_type="ppe_issue",
            entity_id="ppe-1",
            person_id=person.id,
            due_at=now - timedelta(days=100),
            status="closed",
        )
        test_db_session.add_all([deadline_overdue, deadline_upcoming, deadline_closed])

        await test_db_session.commit()

        service = EmployeeCardService(tenant_id=str(tenant.id), db=test_db_session)
        card = await service.build(person.id)
        assert card is not None

        assert card.documents.count == 2
        assert card.documents.signed_count == 1
        assert {item.status for item in card.documents.items} == {
            DocumentStatus.SIGNED,
            DocumentStatus.DRAFT,
        }
        assert any(item.is_signed for item in card.documents.items)
        assert all(
            item.template_name is not None for item in card.documents.items
        ), "template join must hydrate readable names"

        assert card.briefings.count == 2
        assert card.briefings.expired_count == 1
        titles = {item.briefing_template_title for item in card.briefings.items}
        assert "Первичный инструктаж" in titles
        assert any(item.is_expired for item in card.briefings.items)

        assert card.compliance_deadlines.count == 3
        assert card.compliance_deadlines.overdue_count == 1
        assert card.compliance_deadlines.upcoming_count == 1
        statuses = {item.status for item in card.compliance_deadlines.items}
        assert statuses == {"upcoming", "closed"}


@pytest.mark.anyio
class TestEmployeeCardEndpoint:
    async def test_returns_card_for_admin(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Endpoint",
                last_name="User",
                email="endpoint-user@example.com",
            )
            await session.commit()

        headers = _emp_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/employees/{person.id}", headers=headers
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["person_id"] == person.id
        assert body["personal"]["last_name"] == "User"
        assert "training" in body and "medicals" in body and "ppe" in body
        assert "permits" in body and "incidents" in body and "audit" in body
        # vNext-EMP-01 follow-up — Documents/Briefings/Deadlines sections.
        assert "documents" in body and "briefings" in body
        assert "compliance_deadlines" in body
        assert body["documents"]["count"] == 0
        assert body["briefings"]["count"] == 0
        assert body["compliance_deadlines"]["count"] == 0

    async def test_returns_404_for_unknown_employee(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _emp_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/employees/00000000-0000-0000-0000-000000000000",
            headers=headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_forbidden_for_unauthorized_role(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Forbidden",
                last_name="User",
                email="forbidden-user@example.com",
            )
            await session.commit()

        # `student` is not in `_EMPLOYEE_READ_ROLES`.
        headers = _emp_headers(await make_auth_headers(RoleEnum.STUDENT))
        response = await async_client.get(
            f"{API_PREFIX}/employees/{person.id}", headers=headers
        )
        assert response.status_code in {status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED}
