from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant, TrainingPlan, PPEIssue, Inspection
from app.models.notifications import Notification, NotificationChannel, NotificationChannelSettings, NotificationPriority, NotificationStatus, PlanTask

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    id: str
    channel: str
    type: str
    title: str
    body: str
    payload: dict[str, object] | None = None
    priority: str
    status: str
    is_read: bool
    deeplink: str | None = None
    scheduled_at: datetime
    sent_at: datetime | None = None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    next_cursor: str | None = None
    unread_count: int = 0


class MarkReadRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ChannelSettingsIn(BaseModel):
    email_enabled: bool = True
    telegram_enabled: bool = False
    inapp_enabled: bool = True
    email: str | None = None
    telegram_chat_id: str | None = None
    quiet_hours: dict[str, str] | None = None
    digest_mode: str | None = None
    channel_preferences: dict[str, object] | None = None


class ChannelSettingsOut(ChannelSettingsIn):
    user_id: str


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]


@router.get("", response_model=NotificationPage)
async def list_notifications(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> NotificationPage:
    stmt = select(Notification).where(
        Notification.tenant_id == tenant.id,
        Notification.user_id == access.user.id,
        Notification.deleted_at.is_(None),
    )
    if status:
        if status == "unread":
            stmt = stmt.where(Notification.status != NotificationStatus.READ)
        else:
            stmt = stmt.where(Notification.status == NotificationStatus(status))
    if priority:
        stmt = stmt.where(Notification.priority == NotificationPriority(priority))
    if channel:
        stmt = stmt.where(Notification.channel == channel)
    if type:
        stmt = stmt.where(Notification.type == type)
    if cursor:
        stmt = stmt.where(Notification.created_at < datetime.fromisoformat(cursor))
    rows = (await session.execute(stmt.order_by(Notification.created_at.desc()).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    unread_count = (await session.execute(select(Notification).where(Notification.tenant_id == tenant.id, Notification.user_id == access.user.id, Notification.channel == NotificationChannel.INAPP, Notification.deleted_at.is_(None), Notification.status != NotificationStatus.READ))).scalars().all()
    return NotificationPage(
        items=[
            NotificationRead(
                id=item.id,
                channel=item.channel.value,
                type=item.type.value,
                title=item.title,
                body=item.body,
                payload=item.payload,
                priority=item.priority.value if hasattr(item.priority, "value") else str(item.priority),
                status=item.status.value,
                is_read=item.status == NotificationStatus.READ,
                deeplink=str((item.payload or {}).get("deeplink")) if (item.payload or {}).get("deeplink") else None,
                scheduled_at=item.scheduled_at,
                sent_at=item.sent_at,
            )
            for item in items
        ],
        next_cursor=items[-1].created_at.isoformat() if has_more and items else None,
        unread_count=len(unread_count),
    )


@router.post("/mark-read")
async def mark_read(payload: MarkReadRequest, session: SessionDep, tenant: TenantDep, access: AccessDep) -> dict[str, int]:
    updated = 0
    if payload.ids:
        rows = (
            await session.execute(
                select(Notification).where(
                    and_(
                        Notification.tenant_id == tenant.id,
                        Notification.user_id == access.user.id,
                        Notification.id.in_(payload.ids),
                        Notification.channel == "inapp",
                        Notification.deleted_at.is_(None),
                    )
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = NotificationStatus.READ
            row.sent_at = row.sent_at or datetime.now(tz=timezone.utc)
            updated += 1
        await session.flush()
    else:
        rows = (await session.execute(select(Notification).where(Notification.tenant_id == tenant.id, Notification.user_id == access.user.id, Notification.channel == "inapp", Notification.deleted_at.is_(None), Notification.status != NotificationStatus.READ))).scalars().all()
        for row in rows:
            row.status = NotificationStatus.READ
            row.sent_at = row.sent_at or datetime.now(tz=timezone.utc)
            updated += 1
        await session.flush()
    await session.commit()
    return {"updated": updated}


@router.get("/notification-settings/me", response_model=ChannelSettingsOut)
async def get_settings_alias(session: SessionDep, tenant: TenantDep, access: AccessDep) -> ChannelSettingsOut:
    return await get_settings(session=session, tenant=tenant, access=access)


@router.put("/notification-settings/me", response_model=ChannelSettingsOut)
async def put_settings_alias(payload: ChannelSettingsIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> ChannelSettingsOut:
    return await put_settings(payload=payload, session=session, tenant=tenant, access=access)




class CalendarEventRead(BaseModel):
    id: str
    source: str
    entity_type: str
    entity_id: str
    title: str
    date: datetime
    status: str | None = None
    deeplink: str | None = None


@router.get("/calendar/events", response_model=list[CalendarEventRead])
async def list_calendar_events(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> list[CalendarEventRead]:
    events: list[CalendarEventRead] = []

    task_stmt = select(PlanTask).where(
        PlanTask.tenant_id == tenant.id,
        PlanTask.deleted_at.is_(None),
        PlanTask.due_at.is_not(None),
    )
    if status:
        task_stmt = task_stmt.where(PlanTask.status == status)
    task_rows = (await session.execute(task_stmt.order_by(PlanTask.due_at.asc()).limit(300))).scalars().all()
    for row in task_rows:
        if source and source != "task":
            continue
        if row.due_at is None:
            continue
        events.append(CalendarEventRead(
            id=f"task:{row.id}",
            source="task",
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            title=row.title,
            date=_as_utc(row.due_at),
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            deeplink=f"/tasks?entity={row.entity_type}:{row.entity_id}",
        ))

    training_rows = (
        await session.execute(
            select(TrainingPlan).where(TrainingPlan.tenant_id == tenant.id, TrainingPlan.deleted_at.is_(None), TrainingPlan.due_date.is_not(None)).limit(300)
        )
    ).scalars().all()
    for row in training_rows:
        if source and source != "training":
            continue
        if row.due_date is None:
            continue
        events.append(CalendarEventRead(
            id=f"training:{row.id}",
            source="training",
            entity_type="training",
            entity_id=row.id,
            title="Обучение: контрольная дата",
            date=datetime.combine(row.due_date, datetime.min.time(), tzinfo=timezone.utc),
            deeplink=f"/training?id={row.id}",
        ))

    ppe_rows = (
        await session.execute(
            select(PPEIssue).where(PPEIssue.tenant_id == tenant.id, PPEIssue.deleted_at.is_(None), PPEIssue.expires_at.is_not(None)).limit(300)
        )
    ).scalars().all()
    for row in ppe_rows:
        if source and source != "ppe":
            continue
        if row.expires_at is None:
            continue
        events.append(CalendarEventRead(
            id=f"ppe:{row.id}",
            source="ppe",
            entity_type="ppe",
            entity_id=row.id,
            title="СИЗ: окончание срока",
            date=_as_utc(row.expires_at),
            deeplink=f"/ppe?issue={row.id}",
        ))

    inspection_rows = (
        await session.execute(
            select(Inspection).where(Inspection.tenant_id == tenant.id, Inspection.deleted_at.is_(None), Inspection.scheduled_at.is_not(None)).limit(300)
        )
    ).scalars().all()
    for row in inspection_rows:
        if source and source != "inspection":
            continue
        if row.scheduled_at is None:
            continue
        events.append(CalendarEventRead(
            id=f"inspection:{row.id}",
            source="inspection",
            entity_type="inspection",
            entity_id=row.id,
            title="Проверка: запланировано",
            date=datetime.combine(row.scheduled_at, datetime.min.time(), tzinfo=timezone.utc),
            status=row.status.value if hasattr(row.status, "value") else str(row.status),
            deeplink=f"/inspections?id={row.id}",
        ))

    events.sort(key=lambda item: _as_utc(item.date))
    return events[:500]


@router.get("/settings/me", response_model=ChannelSettingsOut)
async def get_settings(session: SessionDep, tenant: TenantDep, access: AccessDep) -> ChannelSettingsOut:
    settings = (
        await session.execute(
            select(NotificationChannelSettings).where(
                NotificationChannelSettings.tenant_id == tenant.id,
                NotificationChannelSettings.user_id == access.user.id,
                NotificationChannelSettings.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if settings is None:
        settings = NotificationChannelSettings(tenant_id=tenant.id, user_id=access.user.id)
        session.add(settings)
        await session.flush()
    await session.commit()
    return ChannelSettingsOut.model_validate(settings, from_attributes=True)


@router.put("/settings/me", response_model=ChannelSettingsOut)
async def put_settings(payload: ChannelSettingsIn, session: SessionDep, tenant: TenantDep, access: AccessDep) -> ChannelSettingsOut:
    settings = (
        await session.execute(
            select(NotificationChannelSettings).where(
                NotificationChannelSettings.tenant_id == tenant.id,
                NotificationChannelSettings.user_id == access.user.id,
                NotificationChannelSettings.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if settings is None:
        settings = NotificationChannelSettings(tenant_id=tenant.id, user_id=access.user.id)
        session.add(settings)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    await session.flush()
    await session.commit()
    return ChannelSettingsOut.model_validate(settings, from_attributes=True)
