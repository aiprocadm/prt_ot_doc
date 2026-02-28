from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select

from app.models.models import RoleEnum, Tenant, TrainingCourse, TrainingPlan, User
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
    PlanTask,
    PlanTaskStatus,
)


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


async def test_notifications_unread_filter_excludes_read(async_client, make_auth_headers, sessionmaker) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    user_email = f"{RoleEnum.ADMIN.value}-api@example.com"

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        user = (await session.execute(select(User).where(User.email == user_email))).scalar_one()

        session.add_all(
            [
                Notification(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    channel=NotificationChannel.INAPP,
                    type=NotificationType.DOCUMENT_GENERATED,
                    title="Unread",
                    body="Unread notification",
                    status=NotificationStatus.SENT,
                    dedup_key=f"{tenant.id}:unread",
                    scheduled_at=datetime.now(tz=timezone.utc),
                ),
                Notification(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    channel=NotificationChannel.INAPP,
                    type=NotificationType.DOCUMENT_GENERATED,
                    title="Read",
                    body="Read notification",
                    status=NotificationStatus.READ,
                    dedup_key=f"{tenant.id}:read",
                    scheduled_at=datetime.now(tz=timezone.utc),
                ),
            ]
        )
        await session.commit()

    response = await async_client.get("/api/v1/notifications", headers=headers, params={"status": "unread"})
    assert response.status_code == 200
    payload = response.json()
    titles = {item["title"] for item in payload["items"]}
    assert "Unread" in titles
    assert "Read" not in titles
