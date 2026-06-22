"""Tests for the Smart Calendar aggregator (vNext-CAL-01 / Phase 4.1)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingTemplate,
    CalendarEvent,
    ComplianceDeadline,
    Inspection,
    InspectionStatus,
    InspectionType,
    MedicalExam,
    Permit,
    PermitStatus,
    PPEIssue,
    PPEIssueStatus,
    RoleEnum,
    TrainingCourse,
    TrainingSession,
    TrainingSessionStatus,
)
from app.services.calendar_aggregator import (
    ALL_SOURCES,
    CalendarAggregatorService,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _cal_headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


@pytest.mark.anyio
class TestCalendarAggregatorService:
    """Service-level tests for `CalendarAggregatorService.list_events`."""

    async def test_returns_empty_when_no_data(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events()
        assert response.total == 0
        assert response.overdue_count == 0
        assert response.items == []
        # Per-source counters present even when all zero, so the UI can
        # still render badges deterministically.
        assert {row.source_type for row in response.by_source} == set(ALL_SOURCES)
        assert all(row.count == 0 for row in response.by_source)

    async def test_isolates_other_tenants(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(slug="cal-tenant-a", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="cal-tenant-b", session=test_db_session)
        company_a = await data_factory.create_company(tenant=tenant_a, session=test_db_session)
        person_a = await data_factory.create_person(
            tenant=tenant_a,
            company=company_a,
            session=test_db_session,
            first_name="Cal",
            last_name="Tenant-A",
            email="cal-tenant-a@example.com",
        )
        today = date.today()
        test_db_session.add(
            MedicalExam(
                tenant_id=tenant_a.id,
                person_id=person_a.id,
                exam_type="periodic",
                exam_date=today - timedelta(days=10),
                valid_until=today + timedelta(days=30),
                conclusion="fit",
            )
        )
        await test_db_session.commit()

        service_other = CalendarAggregatorService(tenant_id=str(tenant_b.id), db=test_db_session)
        response = await service_other.list_events()
        assert response.total == 0
        assert response.items == []

        service_owner = CalendarAggregatorService(tenant_id=str(tenant_a.id), db=test_db_session)
        owned = await service_owner.list_events()
        assert owned.total == 1
        assert owned.items[0].source_type == "medical_exam"

    async def test_aggregates_all_sources(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=test_db_session
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Multi",
            last_name="Source",
            email="multi-source@example.com",
        )

        today = date.today()
        now = datetime.now(timezone.utc)

        # Medical: one current, one expired.
        test_db_session.add_all(
            [
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=10),
                    valid_until=today + timedelta(days=30),
                    conclusion="fit",
                ),
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="psych",
                    exam_date=today - timedelta(days=400),
                    valid_until=today - timedelta(days=10),
                    conclusion="fit",
                ),
            ]
        )

        # PPE: one expiring soon (active+overdue), one returned (excluded
        # from overdue), one with NULL expires_at (skipped entirely).
        test_db_session.add_all(
            [
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Hard hat",
                    quantity=1,
                    issued_at=now - timedelta(days=10),
                    expires_at=now - timedelta(days=2),
                    status=PPEIssueStatus.ISSUED,
                ),
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Boots",
                    quantity=1,
                    issued_at=now - timedelta(days=400),
                    expires_at=now - timedelta(days=300),
                    returned_at=now - timedelta(days=10),
                    status=PPEIssueStatus.RETURNED,
                ),
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Gloves",
                    quantity=1,
                    issued_at=now - timedelta(days=10),
                    expires_at=None,  # excluded from calendar (no anchor).
                    status=PPEIssueStatus.ISSUED,
                ),
            ]
        )

        # Permit: one active, one expired-but-still-ACTIVE.
        test_db_session.add_all(
            [
                Permit(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    permit_type="height_works",
                    issued_at=today - timedelta(days=5),
                    valid_until=today + timedelta(days=10),
                    status=PermitStatus.ACTIVE,
                ),
                Permit(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    permit_type="electrical_4kv",
                    issued_at=today - timedelta(days=400),
                    valid_until=today - timedelta(days=30),
                    status=PermitStatus.ACTIVE,
                ),
            ]
        )

        # Training: one scheduled in the past (overdue), one completed.
        course = TrainingCourse(
            tenant_id=tenant.id,
            title="Промышленная безопасность",
            duration_hours=40,
        )
        test_db_session.add(course)
        await test_db_session.flush()
        test_db_session.add_all(
            [
                TrainingSession(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    course_id=course.id,
                    status=TrainingSessionStatus.SCHEDULED,
                    started_at=now - timedelta(days=5),
                ),
                TrainingSession(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    course_id=course.id,
                    status=TrainingSessionStatus.COMPLETED,
                    started_at=now - timedelta(days=30),
                    completed_at=now - timedelta(days=29),
                    score=90,
                ),
            ]
        )

        # Inspection: one scheduled in the past (PLANNED → overdue), one
        # completed.
        test_db_session.add_all(
            [
                Inspection(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    inspection_type=InspectionType.EXTERNAL,
                    authority="Ростехнадзор",
                    purpose="Плановая",
                    scheduled_at=today - timedelta(days=2),
                    status=InspectionStatus.PLANNED,
                ),
                Inspection(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    inspection_type=InspectionType.INTERNAL,
                    authority="Внутренний аудит",
                    scheduled_at=today - timedelta(days=30),
                    started_at=now - timedelta(days=30),
                    finished_at=now - timedelta(days=29),
                    status=InspectionStatus.COMPLETED,
                ),
            ]
        )

        # Compliance deadline: one overdue, one upcoming, one closed.
        test_db_session.add_all(
            [
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="medical_exam",
                    entity_id="medical-1",
                    person_id=person.id,
                    due_at=now - timedelta(days=3),
                    status="upcoming",
                ),
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="training_session",
                    entity_id="training-1",
                    person_id=person.id,
                    due_at=now + timedelta(days=15),
                    status="upcoming",
                ),
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="ppe_issue",
                    entity_id="ppe-1",
                    person_id=person.id,
                    due_at=now - timedelta(days=100),
                    status="closed",
                ),
            ]
        )

        # Briefing entry: one current, one expired.
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
        test_db_session.add_all(
            [
                BriefingEntry(
                    tenant_id=tenant.id,
                    briefing_journal_id=journal.id,
                    briefing_template_id=briefing_template.id,
                    person_id=person.id,
                    site_id=site.id,
                    briefing_type="primary",
                    briefing_date=now - timedelta(days=10),
                    valid_until=now + timedelta(days=355),
                    status="signed",
                ),
                BriefingEntry(
                    tenant_id=tenant.id,
                    briefing_journal_id=journal.id,
                    briefing_template_id=briefing_template.id,
                    person_id=person.id,
                    site_id=site.id,
                    briefing_type="primary",
                    briefing_date=now - timedelta(days=400),
                    valid_until=now - timedelta(days=30),
                    status="signed",
                ),
            ]
        )

        # Legacy CalendarEvent projection (used by the existing dispatcher).
        test_db_session.add(
            CalendarEvent(
                tenant_id=tenant.id,
                source_type="custom",
                source_id="legacy-1",
                title="Legacy projection",
                starts_at=now + timedelta(days=2),
                site_id=site.id,
                status="active",
            )
        )

        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events()

        # Sanity checks: total is the sum of per-source counts, and items
        # are sorted by anchor.
        per_source = {row.source_type: row for row in response.by_source}
        assert per_source["medical_exam"].count == 2
        assert per_source["medical_exam"].overdue_count == 1
        # Two PPE rows have an expires_at; one is RETURNED so not counted as overdue.
        assert per_source["ppe_issue"].count == 2
        assert per_source["ppe_issue"].overdue_count == 1
        assert per_source["permit"].count == 2
        assert per_source["permit"].overdue_count == 1
        assert per_source["training_session"].count == 2
        assert per_source["training_session"].overdue_count == 1
        assert per_source["inspection"].count == 2
        assert per_source["inspection"].overdue_count == 1
        assert per_source["compliance_deadline"].count == 3
        assert per_source["compliance_deadline"].overdue_count == 1
        assert per_source["briefing_entry"].count == 2
        assert per_source["briefing_entry"].overdue_count == 1
        assert per_source["calendar_event"].count == 1
        assert per_source["calendar_event"].overdue_count == 0

        assert response.total == sum(row.count for row in response.by_source)
        assert response.overdue_count == sum(row.overdue_count for row in response.by_source)

        # Items are sorted ascending by starts_at.
        starts = [item.starts_at for item in response.items]
        assert starts == sorted(starts)

        # Composite ID format makes drill-down deterministic.
        for item in response.items:
            assert item.id == f"{item.source_type}:{item.source_id}"

        # Russian-localized titles for the human-readable streams.
        types = {item.source_type for item in response.items}
        assert {"medical_exam", "ppe_issue", "permit", "training_session"} <= types
        med_titles = [item.title for item in response.items if item.source_type == "medical_exam"]
        assert any(title.startswith("Медосмотр:") for title in med_titles)

    async def test_filters_by_source_type_and_person(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person_alpha = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Alpha",
            last_name="One",
            email="alpha-one@example.com",
        )
        person_beta = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Beta",
            last_name="Two",
            email="beta-two@example.com",
        )

        today = date.today()
        test_db_session.add_all(
            [
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person_alpha.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=5),
                    valid_until=today + timedelta(days=20),
                ),
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person_beta.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=5),
                    valid_until=today + timedelta(days=40),
                ),
                Permit(
                    tenant_id=tenant.id,
                    person_id=person_alpha.id,
                    permit_type="height_works",
                    issued_at=today - timedelta(days=5),
                    valid_until=today + timedelta(days=10),
                    status=PermitStatus.ACTIVE,
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        # Person filter restricts to alpha's two events (medical + permit).
        only_alpha = await service.list_events(person_id=person_alpha.id)
        assert {item.source_type for item in only_alpha.items} == {
            "medical_exam",
            "permit",
        }
        assert all(item.person_id == person_alpha.id for item in only_alpha.items)

        # source_types filter narrows further to the medical only.
        only_alpha_medical = await service.list_events(
            person_id=person_alpha.id, source_types=["medical_exam"]
        )
        assert len(only_alpha_medical.items) == 1
        assert only_alpha_medical.items[0].source_type == "medical_exam"
        # by_source only contains the requested source.
        assert {row.source_type for row in only_alpha_medical.by_source} == {"medical_exam"}

    async def test_filters_by_date_range(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Range",
            last_name="Filter",
            email="range-filter@example.com",
        )

        now = datetime.now(timezone.utc)
        test_db_session.add_all(
            [
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="medical_exam",
                    entity_id="m-1",
                    person_id=person.id,
                    due_at=now + timedelta(days=2),
                    status="upcoming",
                ),
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="training_session",
                    entity_id="t-1",
                    person_id=person.id,
                    due_at=now + timedelta(days=200),  # outside range below.
                    status="upcoming",
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        within_window = await service.list_events(
            from_at=now,
            to_at=now + timedelta(days=14),
            source_types=["compliance_deadline"],
        )
        assert len(within_window.items) == 1
        assert within_window.items[0].extra["entity_type"] == "medical_exam"

    async def test_unknown_source_type_raises(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        with pytest.raises(ValueError):
            await service.list_events(source_types=["nonexistent"])


@pytest.mark.anyio
class TestCalendarEventsEndpoint:
    """Endpoint-level smoke tests for `GET /api/v1/calendar/events`."""

    async def test_returns_200_for_admin_with_no_data(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(f"{API_PREFIX}/calendar/events", headers=headers)
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["total"] == 0
        assert body["overdue_count"] == 0
        assert body["items"] == []
        assert {row["source_type"] for row in body["by_source"]} == set(ALL_SOURCES)

    async def test_aggregates_for_authorized_role(
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
                last_name="Calendar",
                email="endpoint-calendar@example.com",
            )
            today = date.today()
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=5),
                    valid_until=today + timedelta(days=10),
                )
            )
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.HR))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=medical_exam",
            headers=headers,
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["source_type"] == "medical_exam"
        assert item["title"].startswith("Медосмотр:")
        assert item["id"] == f"medical_exam:{item['source_id']}"

    async def test_rejects_unknown_source_type_with_400(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=nope",
            headers=headers,
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_forbidden_for_unauthorized_role(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.STUDENT))
        response = await async_client.get(f"{API_PREFIX}/calendar/events", headers=headers)
        assert response.status_code in {
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        }


@pytest.mark.anyio
class TestCalendarPlanFactComparison:
    """`include_fact=True` populates `expected_at`/`actual_at`/`variance_days`."""

    async def test_default_omits_plan_fact_fields(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Plan",
            last_name="Default",
            email="plan-default@example.com",
        )
        today = date.today()
        test_db_session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=today - timedelta(days=20),
                valid_until=today + timedelta(days=10),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        # Default keeps wire payload identical to the legacy contract.
        response = await service.list_events(source_types=["medical_exam"])
        assert response.total == 1
        item = response.items[0]
        assert item.expected_at is None
        assert item.actual_at is None
        assert item.variance_days is None

    async def test_inspection_completed_emits_variance(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=test_db_session
        )
        today = date.today()
        scheduled_day = today - timedelta(days=10)
        finished_dt = datetime.combine(today - timedelta(days=7), datetime.min.time(), timezone.utc)
        test_db_session.add_all(
            [
                Inspection(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    inspection_type=InspectionType.INTERNAL,
                    authority="Внутренний аудит",
                    scheduled_at=scheduled_day,
                    started_at=finished_dt - timedelta(days=1),
                    finished_at=finished_dt,
                    status=InspectionStatus.COMPLETED,
                ),
                Inspection(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    inspection_type=InspectionType.EXTERNAL,
                    authority="Ростехнадзор",
                    scheduled_at=today + timedelta(days=5),
                    status=InspectionStatus.PLANNED,
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["inspection"], include_fact=True)
        items = {item.title: item for item in response.items}
        assert "Проверка: Внутренний аудит" in items
        completed = items["Проверка: Внутренний аудит"]
        assert completed.expected_at is not None
        assert completed.expected_at.date() == scheduled_day
        assert completed.actual_at == finished_dt
        # finished 3 days after scheduled.
        assert completed.variance_days == 3

        planned = items["Проверка: Ростехнадзор"]
        # Plan-only row keeps actual_at/variance None even with include_fact.
        assert planned.expected_at is not None
        assert planned.actual_at is None
        assert planned.variance_days is None

    async def test_training_completed_emits_actual_at(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Plan",
            last_name="Training",
            email="plan-training@example.com",
        )
        course = TrainingCourse(
            tenant_id=tenant.id,
            title="Промбезопасность",
            duration_hours=16,
        )
        test_db_session.add(course)
        await test_db_session.flush()

        now = datetime.now(timezone.utc)
        test_db_session.add_all(
            [
                TrainingSession(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    course_id=course.id,
                    status=TrainingSessionStatus.COMPLETED,
                    started_at=now - timedelta(days=5),
                    completed_at=now - timedelta(days=3),
                ),
                TrainingSession(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    course_id=course.id,
                    status=TrainingSessionStatus.SCHEDULED,
                    started_at=now + timedelta(days=2),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["training_session"], include_fact=True)
        statuses = {item.status: item for item in response.items}
        completed = statuses["completed"]
        assert completed.expected_at is not None
        assert completed.actual_at is not None
        assert completed.variance_days == 2  # completed_at - started_at = +2 days
        scheduled = statuses["scheduled"]
        assert scheduled.actual_at is None
        assert scheduled.variance_days is None

    async def test_ppe_returned_emits_variance(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Plan",
            last_name="Ppe",
            email="plan-ppe@example.com",
        )
        now = datetime.now(timezone.utc)
        test_db_session.add_all(
            [
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Каска",
                    quantity=1,
                    issued_at=now - timedelta(days=400),
                    expires_at=now - timedelta(days=10),
                    returned_at=now - timedelta(days=5),  # returned 5 days late
                    status=PPEIssueStatus.RETURNED,
                ),
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Перчатки",
                    quantity=1,
                    issued_at=now - timedelta(days=10),
                    expires_at=now + timedelta(days=20),
                    status=PPEIssueStatus.ISSUED,
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["ppe_issue"], include_fact=True)
        by_name = {item.title: item for item in response.items}
        returned = by_name["СИЗ: Каска"]
        assert returned.actual_at is not None
        # returned_at is 5 days after expires_at → variance = +5
        assert returned.variance_days == 5
        active = by_name["СИЗ: Перчатки"]
        # ISSUED row has no fact data even with include_fact.
        assert active.actual_at is None
        assert active.variance_days is None

    async def test_endpoint_passes_include_fact_query_param(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            site = await data_factory.create_site(tenant=tenant, company=company, session=session)
            today = date.today()
            session.add(
                Inspection(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    inspection_type=InspectionType.INTERNAL,
                    authority="Аудит",
                    scheduled_at=today - timedelta(days=4),
                    finished_at=datetime.combine(
                        today - timedelta(days=2),
                        datetime.min.time(),
                        timezone.utc,
                    ),
                    status=InspectionStatus.COMPLETED,
                )
            )
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        # Without include_fact: legacy payload (None values).
        response_legacy = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=inspection",
            headers=headers,
        )
        assert response_legacy.status_code == status.HTTP_200_OK, response_legacy.text
        legacy_item = response_legacy.json()["items"][0]
        assert legacy_item["expected_at"] is None
        assert legacy_item["actual_at"] is None
        assert legacy_item["variance_days"] is None

        # With include_fact=true: variance computed.
        response_fact = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=inspection&include_fact=true",
            headers=headers,
        )
        assert response_fact.status_code == status.HTTP_200_OK, response_fact.text
        fact_item = response_fact.json()["items"][0]
        assert fact_item["expected_at"] is not None
        assert fact_item["actual_at"] is not None
        assert fact_item["variance_days"] == 2


@pytest.mark.anyio
class TestCalendarSlaTracking:
    """`include_sla=True` populates `days_to_due`/`sla_band` per source thresholds."""

    async def test_default_omits_sla_fields(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Sla",
            last_name="Default",
            email="sla-default@example.com",
        )
        today = date.today()
        test_db_session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=today - timedelta(days=10),
                valid_until=today + timedelta(days=15),
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        # Without `include_sla` the wire payload stays identical to the
        # pre-vNext-CAL-01 contract.
        response = await service.list_events(source_types=["medical_exam"])
        item = response.items[0]
        assert item.days_to_due is None
        assert item.sla_band is None

    async def test_medical_bands_critical_warning_ok(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Sla",
            last_name="Bands",
            email="sla-bands@example.com",
        )
        # Anchor on the UTC date the aggregator will see — using
        # `date.today()` would drift relative to `_utcnow()` for
        # tests run near local midnight in non-UTC timezones.
        today_utc = datetime.now(timezone.utc).date()
        test_db_session.add_all(
            [
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="critical",
                    exam_date=today_utc - timedelta(days=300),
                    # 3 days to expiry → within (≤7) critical window
                    valid_until=today_utc + timedelta(days=3),
                ),
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="warning",
                    exam_date=today_utc - timedelta(days=300),
                    # 20 days → within (≤30) outer warning window
                    valid_until=today_utc + timedelta(days=20),
                ),
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="ok",
                    exam_date=today_utc - timedelta(days=300),
                    # 60 days → beyond warning window → ok
                    valid_until=today_utc + timedelta(days=60),
                ),
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="overdue",
                    exam_date=today_utc - timedelta(days=400),
                    # already past → overdue (negative days_to_due)
                    valid_until=today_utc - timedelta(days=2),
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["medical_exam"], include_sla=True)
        by_type = {item.extra["exam_type"]: item for item in response.items}

        critical = by_type["critical"]
        assert critical.days_to_due is not None
        assert 2 <= critical.days_to_due <= 3  # tolerate a 1-day clock drift
        assert critical.sla_band == "critical"

        warning = by_type["warning"]
        assert warning.days_to_due is not None
        assert 19 <= warning.days_to_due <= 20
        assert warning.sla_band == "warning"

        ok_item = by_type["ok"]
        assert ok_item.days_to_due is not None
        assert 59 <= ok_item.days_to_due <= 60
        assert ok_item.sla_band == "ok"

        # `is_overdue=True` always wins, even though days_to_due is also negative.
        overdue = by_type["overdue"]
        assert overdue.days_to_due is not None
        assert -3 <= overdue.days_to_due <= -2
        assert overdue.sla_band == "overdue"
        assert overdue.is_overdue is True

    async def test_compliance_deadline_uses_tighter_thresholds(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        # ComplianceDeadline thresholds are (3, 14) — tighter than the
        # default (7, 30). A 5-day-out deadline must land in `warning`,
        # not `critical`, even though the same 5-day delta is `critical`
        # for medicals/permits.
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        now = datetime.now(timezone.utc)
        test_db_session.add_all(
            [
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="medical_exam",
                    entity_id="ent-critical",
                    due_at=now + timedelta(days=2),
                    status="open",
                ),
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="medical_exam",
                    entity_id="ent-warning",
                    due_at=now + timedelta(days=5),
                    status="open",
                ),
                ComplianceDeadline(
                    tenant_id=tenant.id,
                    entity_type="medical_exam",
                    entity_id="ent-ok",
                    due_at=now + timedelta(days=20),
                    status="open",
                ),
            ]
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(source_types=["compliance_deadline"], include_sla=True)
        by_entity = {item.extra["entity_id"]: item for item in response.items}
        assert by_entity["ent-critical"].sla_band == "critical"
        assert by_entity["ent-warning"].sla_band == "warning"
        assert by_entity["ent-ok"].sla_band == "ok"

    async def test_combined_with_include_fact(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        # Both flags are independent; turning on both populates plan/fact
        # *and* SLA fields side-by-side without interference.
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=test_db_session
        )
        today_utc = datetime.now(timezone.utc).date()
        scheduled = today_utc + timedelta(days=4)
        test_db_session.add(
            Inspection(
                tenant_id=tenant.id,
                company_id=company.id,
                site_id=site.id,
                inspection_type=InspectionType.INTERNAL,
                authority="SLA-test",
                scheduled_at=scheduled,
                status=InspectionStatus.PLANNED,
            )
        )
        await test_db_session.commit()

        service = CalendarAggregatorService(tenant_id=str(tenant.id), db=test_db_session)
        response = await service.list_events(
            source_types=["inspection"], include_fact=True, include_sla=True
        )
        item = response.items[0]
        # Plan/fact populated (expected_at mirrors anchor; actual_at None
        # for PLANNED row).
        assert item.expected_at is not None
        assert item.actual_at is None
        assert item.variance_days is None
        # SLA populated (4 days → ≤7 inspection critical window).
        assert item.days_to_due is not None
        assert 3 <= item.days_to_due <= 4
        assert item.sla_band == "critical"

    async def test_endpoint_passes_include_sla_query_param(
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
                first_name="Sla",
                last_name="Endpoint",
                email="sla-endpoint@example.com",
            )
            today_utc = datetime.now(timezone.utc).date()
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=today_utc - timedelta(days=10),
                    valid_until=today_utc + timedelta(days=10),
                )
            )
            await session.commit()

        headers = _cal_headers(await make_auth_headers(RoleEnum.ADMIN))
        # Without include_sla the wire payload omits SLA fields.
        legacy = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=medical_exam",
            headers=headers,
        )
        assert legacy.status_code == status.HTTP_200_OK, legacy.text
        legacy_item = legacy.json()["items"][0]
        assert legacy_item["days_to_due"] is None
        assert legacy_item["sla_band"] is None

        # With include_sla=true the server returns days_to_due + band.
        sla = await async_client.get(
            f"{API_PREFIX}/calendar/events?source_types=medical_exam&include_sla=true",
            headers=headers,
        )
        assert sla.status_code == status.HTTP_200_OK, sla.text
        sla_item = sla.json()["items"][0]
        assert sla_item["days_to_due"] is not None
        assert 9 <= sla_item["days_to_due"] <= 10
        # 9-10 days → within medical (7, 30) ⇒ warning band.
        assert sla_item["sla_band"] == "warning"
