from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.models import RoleEnum, TrainingPlan, TrainingCourse
from app.models.notifications import PlanTask, PlanTaskStatus


async def test_calendar_events_returns_training_and_tasks(async_client, make_auth_headers, sessionmaker, data_factory) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(session=session, tenant=tenant)
        course = TrainingCourse(tenant_id=tenant.id, title="Core")
        session.add(course)
        await session.flush()
        training = TrainingPlan(
            tenant_id=tenant.id,
            company_id=company.id,
            course_id=course.id,
            due_date=date.today(),
        )
        session.add(training)
        session.add(
            PlanTask(
                tenant_id=tenant.id,
                title="Training follow-up",
                entity_type="training",
                entity_id="entity-1",
                assignee_id=None,
                status=PlanTaskStatus.OPEN,
                due_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/notifications/calendar/events", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert any(item["source"] == "training" for item in payload)
    assert any(item["source"] == "task" for item in payload)
