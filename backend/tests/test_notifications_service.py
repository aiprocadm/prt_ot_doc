from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, String, Table, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import SharedBase, TenantBase
from app.models.models import Tenant
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.modules.notifications.schemas import NotificationTemplateIn
from app.modules.notifications.service import NotificationApplicationService


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS public"))
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_notifications_counts_unread_and_marks_read(db_session) -> None:
    tenant = Tenant(id="tenant-1", name="Tenant 1", slug="tenant-1", contact_email="tenant@example.com")
    db_session.add(tenant)
    db_session.add_all(
        [
            Notification(
                tenant_id=tenant.id,
                user_id="user-1",
                channel=NotificationChannel.INAPP,
                type=NotificationType.APPROVAL_DEADLINE,
                title="Need approval",
                body="Deadline tomorrow",
                priority=NotificationPriority.HIGH,
                status=NotificationStatus.QUEUED,
                dedup_key="n-1",
                scheduled_at=datetime.now(tz=timezone.utc),
            ),
            Notification(
                tenant_id=tenant.id,
                user_id="user-1",
                channel=NotificationChannel.INAPP,
                type=NotificationType.DOCUMENT_GENERATED,
                title="Generated",
                body="Document ready",
                priority=NotificationPriority.MEDIUM,
                status=NotificationStatus.READ,
                dedup_key="n-2",
                scheduled_at=datetime.now(tz=timezone.utc),
            ),
        ]
    )
    await db_session.commit()

    service = NotificationApplicationService(db_session, tenant, "user-1")
    page = await service.list_notifications(
        status_value="unread",
        priority_value=None,
        channel_value=None,
        type_value=None,
        limit=20,
        cursor=None,
    )

    assert page.unread_count == 1
    assert len(page.items) == 1
    assert page.items[0].is_read is False

    updated = await service.mark_read([])
    assert updated == 1

    page_after = await service.list_notifications(
        status_value=None,
        priority_value=None,
        channel_value=None,
        type_value=None,
        limit=20,
        cursor=None,
    )
    assert page_after.unread_count == 0


@pytest.mark.asyncio
async def test_notifications_service_rejects_unknown_filters(db_session) -> None:
    tenant = Tenant(id="tenant-1", name="Tenant 1", slug="tenant-1", contact_email="tenant@example.com")
    db_session.add(tenant)
    await db_session.commit()

    service = NotificationApplicationService(db_session, tenant, "user-1")

    with pytest.raises(HTTPException) as exc:
        await service.list_notifications(
            status_value=None,
            priority_value="urgent",
            channel_value=None,
            type_value=None,
            limit=20,
            cursor=None,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["details"]["provided"] == "urgent"
    assert "allowed_values" in exc.value.detail["details"]


@pytest.mark.asyncio
async def test_upsert_template_validates_channel_and_type(db_session) -> None:
    tenant = Tenant(id="tenant-1", name="Tenant 1", slug="tenant-1", contact_email="tenant@example.com")
    db_session.add(tenant)
    await db_session.commit()

    service = NotificationApplicationService(db_session, tenant, "user-1")

    with pytest.raises(HTTPException) as exc:
        await service.upsert_template(
            NotificationTemplateIn(
                code="tpl-1",
                channel="fax",
                type="ApprovalDeadline",
                body_template="Body",
            )
        )

    assert exc.value.status_code == 422
    assert exc.value.detail["field_errors"][0]["field"] == "channel"
