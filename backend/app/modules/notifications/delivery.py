"""Notification delivery orchestration (RC-011).

Turns QUEUED :class:`Notification` rows into honest delivery outcomes via per-channel
providers, and — when a delivery fails terminally — escalates by re-queuing the message
on the next enabled channel of the fallback chain (email → telegram → in-app). In-app is
the terminal link (always delivered), so the chain always converges.

No schema change: delivery bookkeeping is written to the existing ``payload`` JSON and the
existing ``status`` / ``attempts`` / ``last_error`` / ``sent_at`` columns.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import User
from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationChannelSettings,
    NotificationStatus,
)
from app.modules.notifications.providers import (
    DeliveryResult,
    EmailProvider,
    InAppProvider,
    NotificationContact,
    NotificationProvider,
    TelegramProvider,
    WebhookProvider,
)
from app.services.notifications import send_notification

logger = logging.getLogger(__name__)

# Fallback order used by channel-tier escalation. In-app is terminal (always delivered).
ESCALATION_CHAIN: tuple[NotificationChannel, ...] = (
    NotificationChannel.EMAIL,
    NotificationChannel.TELEGRAM,
    NotificationChannel.INAPP,
)


def resolve_provider(channel: NotificationChannel, settings) -> NotificationProvider:
    if channel == NotificationChannel.EMAIL:
        return EmailProvider(settings)
    if channel == NotificationChannel.TELEGRAM:
        return TelegramProvider(settings)
    if channel == NotificationChannel.WEBHOOK:
        return WebhookProvider(settings)
    return InAppProvider()


async def resolve_contact(
    session: AsyncSession, tenant_id: str, user_id: str
) -> tuple[NotificationContact, NotificationChannelSettings | None]:
    chan_settings = (
        await session.execute(
            select(NotificationChannelSettings).where(
                NotificationChannelSettings.tenant_id == tenant_id,
                NotificationChannelSettings.user_id == user_id,
                NotificationChannelSettings.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    email = chan_settings.email if chan_settings else None
    telegram_chat_id = chan_settings.telegram_chat_id if chan_settings else None
    if not email:
        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        email = getattr(user, "email", None) if user is not None else None
    return NotificationContact(email=email, telegram_chat_id=telegram_chat_id), chan_settings


def _channel_enabled(
    channel: NotificationChannel, chan_settings: NotificationChannelSettings | None
) -> bool:
    if chan_settings is None:
        # Model defaults: email + in-app on, telegram off.
        return channel in {NotificationChannel.EMAIL, NotificationChannel.INAPP}
    if channel == NotificationChannel.EMAIL:
        return bool(chan_settings.email_enabled)
    if channel == NotificationChannel.TELEGRAM:
        return bool(chan_settings.telegram_enabled)
    if channel == NotificationChannel.INAPP:
        return bool(chan_settings.inapp_enabled)
    return True


def next_escalation_channel(
    current: NotificationChannel, chan_settings: NotificationChannelSettings | None
) -> NotificationChannel | None:
    """Next enabled channel after ``current`` in the fallback chain, or None if exhausted."""
    if current not in ESCALATION_CHAIN:
        return None
    start = ESCALATION_CHAIN.index(current) + 1
    for candidate in ESCALATION_CHAIN[start:]:
        # In-app is the guaranteed terminal fallback even if a user disabled it.
        if candidate == NotificationChannel.INAPP or _channel_enabled(candidate, chan_settings):
            return candidate
    return None


async def _escalate(
    session: AsyncSession,
    notification: Notification,
    chan_settings: NotificationChannelSettings | None,
) -> None:
    nxt = next_escalation_channel(notification.channel, chan_settings)
    if nxt is None:
        return
    tier = int((notification.payload or {}).get("escalation_tier", 0)) + 1
    await send_notification(
        session,
        tenant_id=str(notification.tenant_id),
        user_id=notification.user_id,
        channel=nxt,
        type=notification.type,
        title=notification.title,
        body=notification.body,
        payload={
            **(notification.payload or {}),
            "escalation_tier": tier,
            "escalated_from": notification.id,
        },
        priority=notification.priority,
        dedup_key=f"{notification.dedup_key}:esc{tier}",
        # next_escalation_channel already vetted this channel (an enabled channel or
        # the guaranteed-terminal in-app one); force delivery so a disabled in-app
        # opt-out cannot silently swallow the escalation.
        force=True,
    )
    logger.info(
        "notifications.escalated",
        extra={
            "notification_id": notification.id,
            "from_channel": notification.channel.value,
            "to_channel": nxt.value,
            "tier": tier,
        },
    )


async def deliver_notification(
    session: AsyncSession, notification: Notification, *, settings=None
) -> DeliveryResult:
    """Attempt delivery of one QUEUED notification and record an honest status.

    DELIVERED → ``sent``; SKIPPED (disabled/unconfigured/no contact) → ``sent`` (the row is
    still shown in-app) with the skip reason recorded; FAILED → retry while attempts remain,
    then ``failed`` + channel-tier escalation.
    """
    settings = settings or get_settings()
    contact, chan_settings = await resolve_contact(
        session, str(notification.tenant_id), notification.user_id
    )
    provider = resolve_provider(notification.channel, settings)
    result = await provider.deliver(notification=notification, contact=contact)

    notification.attempts = int(notification.attempts or 0) + 1
    payload = dict(notification.payload or {})
    delivery_meta: dict[str, object] = {
        "channel": notification.channel.value,
        "outcome": result.outcome.value,
        "attempt": notification.attempts,
    }
    if result.detail:
        delivery_meta["detail"] = result.detail
    if result.provider_ref:
        delivery_meta["provider_ref"] = result.provider_ref
    payload["delivery"] = delivery_meta
    notification.payload = payload  # new dict identity so the JSON column is flagged dirty

    now = datetime.now(tz=timezone.utc)
    if result.delivered:
        notification.status = NotificationStatus.SENT
        notification.sent_at = now
        notification.last_error = None
    elif result.skipped:
        notification.status = NotificationStatus.SENT
        notification.sent_at = now
        notification.last_error = result.detail
    else:  # failed
        notification.last_error = result.detail
        max_attempts = int(getattr(settings, "notifications_max_delivery_attempts", 3))
        if notification.attempts >= max_attempts:
            notification.status = NotificationStatus.FAILED
            await _escalate(session, notification, chan_settings)
        else:
            notification.status = NotificationStatus.QUEUED  # keep queued for another attempt

    await session.flush()
    return result


async def scan_pending_notifications(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 200
) -> int:
    """Deliver all due QUEUED notifications for the current tenant session; return the count."""
    now = now or datetime.now(tz=timezone.utc)
    settings = get_settings()
    rows = list(
        (
            await session.execute(
                select(Notification)
                .where(
                    Notification.status == NotificationStatus.QUEUED,
                    Notification.deleted_at.is_(None),
                    Notification.scheduled_at <= now,
                )
                .order_by(Notification.scheduled_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    processed = 0
    for notification in rows:
        await deliver_notification(session, notification, settings=settings)
        processed += 1
    await session.flush()
    return processed
