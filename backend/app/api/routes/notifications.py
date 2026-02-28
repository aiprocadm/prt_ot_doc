from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant
from app.models.notifications import Notification, NotificationChannelSettings, NotificationStatus

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    id: str
    channel: str
    type: str
    title: str
    body: str
    payload: dict[str, object] | None = None
    status: str
    scheduled_at: datetime
    sent_at: datetime | None = None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    next_cursor: str | None = None


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


class ChannelSettingsOut(ChannelSettingsIn):
    user_id: str


SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]


@router.get("", response_model=NotificationPage)
async def list_notifications(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> NotificationPage:
    stmt = select(Notification).where(
        Notification.tenant_id == tenant.id,
        Notification.user_id == access.user.id,
        Notification.deleted_at.is_(None),
    )
    if status:
        stmt = stmt.where(Notification.status == NotificationStatus(status))
    if cursor:
        stmt = stmt.where(Notification.created_at < datetime.fromisoformat(cursor))
    rows = (await session.execute(stmt.order_by(Notification.created_at.desc()).limit(limit + 1))).scalars().all()
    has_more = len(rows) > limit
    items = rows[:limit]
    return NotificationPage(
        items=[
            NotificationRead(
                id=item.id,
                channel=item.channel.value,
                type=item.type.value,
                title=item.title,
                body=item.body,
                payload=item.payload,
                status=item.status.value,
                scheduled_at=item.scheduled_at,
                sent_at=item.sent_at,
            )
            for item in items
        ],
        next_cursor=items[-1].created_at.isoformat() if has_more and items else None,
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
    return {"updated": updated}


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
    return ChannelSettingsOut.model_validate(settings, from_attributes=True)
