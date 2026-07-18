"""RC-011: notification delivery orchestration, honest status and channel-tier escalation."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.modules.notifications import delivery as delivery_mod
from app.modules.notifications.delivery import (
    deliver_notification,
    next_escalation_channel,
    scan_pending_notifications,
)
from app.modules.notifications.providers import (
    DeliveryResult,
    EmailProvider,
    TelegramProvider,
    WebhookProvider,
)
from app.modules.notifications.providers.base import NotificationContact

pytestmark = pytest.mark.asyncio


def _settings(*, enabled: bool = False, max_attempts: int = 3, **extra) -> SimpleNamespace:
    base = dict(
        notifications_delivery_enabled=enabled,
        notifications_max_delivery_attempts=max_attempts,
        smtp_host="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        smtp_from="",
        smtp_use_tls=True,
        admin_email="admin@example.com",
        telegram_bot_token="",
        webhook_notification_url=None,
        inbound_webhook_hmac_secret="",
    )
    base.update(extra)
    return SimpleNamespace(**base)


class _FakeProvider:
    def __init__(self, result: DeliveryResult) -> None:
        self._result = result

    async def deliver(self, *, notification, contact) -> DeliveryResult:
        return self._result


async def _make_notification(
    session, data_factory, *, channel=NotificationChannel.INAPP, email="rc011@example.com"
) -> Notification:
    tenant = await data_factory.ensure_tenant(session=session)
    user = await data_factory.create_user(tenant=tenant, email=email, session=session)
    note = Notification(
        tenant_id=tenant.id,
        user_id=user.id,
        channel=channel,
        type=NotificationType.APPROVAL_DEADLINE,
        title="Delivery test",
        body="Please act",
        priority=NotificationPriority.HIGH,
        status=NotificationStatus.QUEUED,
        dedup_key=f"rc011-{channel.value}",
        scheduled_at=datetime.now(tz=timezone.utc),
    )
    session.add(note)
    await session.flush()
    return note


# --- pure escalation-chain logic -----------------------------------------------------


def test_next_escalation_channel_defaults_skip_disabled_telegram():
    # No settings row -> model defaults (telegram off) -> email escalates straight to in-app.
    assert next_escalation_channel(NotificationChannel.EMAIL, None) == NotificationChannel.INAPP
    assert next_escalation_channel(NotificationChannel.TELEGRAM, None) == NotificationChannel.INAPP
    assert next_escalation_channel(NotificationChannel.INAPP, None) is None
    assert next_escalation_channel(NotificationChannel.WEBHOOK, None) is None


def test_next_escalation_channel_uses_enabled_telegram():
    row = SimpleNamespace(email_enabled=True, telegram_enabled=True, inapp_enabled=True)
    assert next_escalation_channel(NotificationChannel.EMAIL, row) == NotificationChannel.TELEGRAM


# --- provider skip paths (no network) ------------------------------------------------


async def test_email_provider_skips_when_disabled():
    res = await EmailProvider(_settings(enabled=False, smtp_host="smtp.local")).deliver(
        notification=SimpleNamespace(title="t", body="b"),
        contact=NotificationContact(email="x@example.com"),
    )
    assert res.skipped


async def test_email_provider_skips_without_recipient():
    res = await EmailProvider(_settings(enabled=True, smtp_host="smtp.local")).deliver(
        notification=SimpleNamespace(title="t", body="b"),
        contact=NotificationContact(email=None),
    )
    assert res.skipped and "email" in (res.detail or "")


async def test_telegram_provider_skips_without_chat_id():
    res = await TelegramProvider(_settings(enabled=True, telegram_bot_token="tok")).deliver(
        notification=SimpleNamespace(title="t", body="b"),
        contact=NotificationContact(telegram_chat_id=None),
    )
    assert res.skipped


async def test_webhook_provider_skips_when_url_missing():
    res = await WebhookProvider(_settings(enabled=True, webhook_notification_url="")).deliver(
        notification=SimpleNamespace(
            id="1",
            tenant_id="t",
            user_id="u",
            type=NotificationType.APPROVAL_DEADLINE,
            title="t",
            body="b",
            priority=NotificationPriority.HIGH,
            payload=None,
        ),
        contact=NotificationContact(),
    )
    assert res.skipped


# --- orchestration -------------------------------------------------------------------


async def test_inapp_delivery_marks_sent(sessionmaker, data_factory):
    async with sessionmaker() as session:
        note = await _make_notification(session, data_factory, channel=NotificationChannel.INAPP)
        result = await deliver_notification(session, note, settings=_settings(enabled=True))
    assert result.delivered
    assert note.status == NotificationStatus.SENT
    assert note.sent_at is not None
    assert note.payload["delivery"]["outcome"] == "delivered"


async def test_email_disabled_marks_sent_but_records_skip(sessionmaker, data_factory):
    # Default OFF: not a false external SEND — recorded as skipped, still visible in-app.
    async with sessionmaker() as session:
        note = await _make_notification(session, data_factory, channel=NotificationChannel.EMAIL)
        await deliver_notification(session, note, settings=_settings(enabled=False))
    assert note.status == NotificationStatus.SENT
    assert note.payload["delivery"]["outcome"] == "skipped"
    assert "disabled" in (note.last_error or "")


async def test_email_success_via_provider(sessionmaker, data_factory, monkeypatch):
    monkeypatch.setattr(
        delivery_mod,
        "resolve_provider",
        lambda channel, settings: _FakeProvider(DeliveryResult.ok("ref-1")),
    )
    async with sessionmaker() as session:
        note = await _make_notification(session, data_factory, channel=NotificationChannel.EMAIL)
        await deliver_notification(session, note, settings=_settings(enabled=True))
    assert note.status == NotificationStatus.SENT
    assert note.payload["delivery"]["provider_ref"] == "ref-1"


async def test_failed_delivery_retries_then_escalates(sessionmaker, data_factory, monkeypatch):
    monkeypatch.setattr(
        delivery_mod,
        "resolve_provider",
        lambda channel, settings: _FakeProvider(DeliveryResult.fail("smtp down")),
    )
    async with sessionmaker() as session:
        note = await _make_notification(session, data_factory, channel=NotificationChannel.EMAIL)
        # attempt 1 of 2: stays queued for retry, no escalation yet
        await deliver_notification(session, note, settings=_settings(enabled=True, max_attempts=2))
        assert note.status == NotificationStatus.QUEUED and note.attempts == 1
        # attempt 2 of 2: terminal failure -> FAILED + escalation to next channel
        await deliver_notification(session, note, settings=_settings(enabled=True, max_attempts=2))
        assert note.status == NotificationStatus.FAILED and note.attempts == 2
        assert note.last_error == "smtp down"

        escalated = (
            (
                await session.execute(
                    select(Notification).where(
                        Notification.tenant_id == note.tenant_id,
                        Notification.id != note.id,
                        Notification.status == NotificationStatus.QUEUED,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(escalated) == 1
    esc = escalated[0]
    # email -> (telegram off by default) -> in-app terminal fallback
    assert esc.channel == NotificationChannel.INAPP
    assert esc.payload["escalation_tier"] == 1
    assert esc.payload["escalated_from"] == note.id


async def test_scan_delivers_due_queued(sessionmaker, data_factory):
    async with sessionmaker() as session:
        n1 = await _make_notification(session, data_factory, channel=NotificationChannel.INAPP)
        n2 = Notification(
            tenant_id=n1.tenant_id,
            user_id=n1.user_id,
            channel=NotificationChannel.INAPP,
            type=NotificationType.APPROVAL_DEADLINE,
            title="Second",
            body="body",
            priority=NotificationPriority.MEDIUM,
            status=NotificationStatus.QUEUED,
            dedup_key="rc011-scan-2",
            scheduled_at=datetime.now(tz=timezone.utc),
        )
        session.add(n2)
        await session.flush()

        processed = await scan_pending_notifications(session)
        assert processed == 2

        remaining_queued = (
            (
                await session.execute(
                    select(Notification).where(
                        Notification.tenant_id == n1.tenant_id,
                        Notification.status == NotificationStatus.QUEUED,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert remaining_queued == []
