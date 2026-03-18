from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationChannelSettings,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


def build_dedup_key(*, tenant_id: str, user_id: str, type: NotificationType, entity_type: str | None, entity_id: str | None, bucket: str) -> str:
    return f"{tenant_id}:{user_id}:{type.value}:{entity_type or '-'}:{entity_id or '-'}:{bucket}"


def apply_quiet_hours(scheduled_at: datetime, quiet_hours: dict[str, str] | None) -> datetime:
    if not quiet_hours:
        return scheduled_at
    try:
        tz = ZoneInfo(quiet_hours.get("tz", "UTC"))
        from_t = time.fromisoformat(quiet_hours["from"])
        to_t = time.fromisoformat(quiet_hours["to"])
    except Exception:
        return scheduled_at

    local = scheduled_at.astimezone(tz)
    current = local.timetz().replace(tzinfo=None)
    in_quiet = from_t <= current or current < to_t if from_t > to_t else from_t <= current < to_t
    if not in_quiet:
        return scheduled_at

    next_date = local.date()
    if current >= from_t:
        next_date = local.date() + timedelta(days=1)
    shifted = datetime.combine(next_date, to_t, tzinfo=tz)
    return shifted.astimezone(timezone.utc)


async def send_notification(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    channel: NotificationChannel,
    type: NotificationType,
    title: str,
    body: str,
    payload: dict[str, object] | None = None,
    scheduled_at: datetime | None = None,
    dedup_key: str | None = None,
    priority: NotificationPriority = NotificationPriority.MEDIUM,
) -> Notification | None:
    scheduled_at = scheduled_at or datetime.now(tz=timezone.utc)
    settings = (
        await session.execute(
            select(NotificationChannelSettings).where(
                and_(
                    NotificationChannelSettings.tenant_id == tenant_id,
                    NotificationChannelSettings.user_id == user_id,
                    NotificationChannelSettings.deleted_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()

    if settings:
        if channel == NotificationChannel.EMAIL and not settings.email_enabled:
            return None
        if channel == NotificationChannel.TELEGRAM and not settings.telegram_enabled:
            return None
        if channel == NotificationChannel.INAPP and not settings.inapp_enabled:
            return None
        scheduled_at = apply_quiet_hours(scheduled_at, settings.quiet_hours)

    if dedup_key:
        existing = (
            await session.execute(
                select(Notification).where(Notification.dedup_key == dedup_key, Notification.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if existing:
            return existing

    item = Notification(
        tenant_id=tenant_id,
        user_id=user_id,
        channel=channel,
        type=type,
        title=title,
        body=body,
        payload=payload,
        priority=priority,
        status=NotificationStatus.QUEUED,
        dedup_key=dedup_key or build_dedup_key(
            tenant_id=tenant_id,
            user_id=user_id,
            type=type,
            entity_type=str((payload or {}).get("entity_type") or ""),
            entity_id=str((payload or {}).get("entity_id") or ""),
            bucket=scheduled_at.strftime("%Y%m%d%H"),
        ),
        scheduled_at=scheduled_at,
    )
    session.add(item)
    await session.flush()
    return item
