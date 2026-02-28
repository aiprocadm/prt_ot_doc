from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.notifications import NotificationChannel, NotificationChannelSettings, NotificationType
from app.services.notifications import apply_quiet_hours, build_dedup_key, send_notification


def test_build_dedup_key() -> None:
    key = build_dedup_key(
        tenant_id="t1",
        user_id="u1",
        type=NotificationType.TRAINING_DUE_SOON,
        entity_type="training",
        entity_id="e1",
        bucket="20260316",
    )
    assert key == "t1:u1:TrainingDueSoon:training:e1:20260316"


def test_apply_quiet_hours_rolls_to_window_end() -> None:
    ts = datetime(2026, 3, 16, 22, 30, tzinfo=timezone.utc)
    shifted = apply_quiet_hours(ts, {"from": "22:00", "to": "08:00", "tz": "UTC"})
    assert shifted.hour == 8
    assert shifted.date() == (ts + timedelta(days=1)).date()


@pytest.mark.anyio
async def test_send_notification_deduplicates(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(session=session, tenant=tenant)
        session.add(NotificationChannelSettings(tenant_id=tenant.id, user_id=user.id))
        await session.flush()

        dedup = "dup-1"
        first = await send_notification(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            channel=NotificationChannel.INAPP,
            type=NotificationType.DOCUMENT_GENERATED,
            title="a",
            body="b",
            dedup_key=dedup,
        )
        second = await send_notification(
            session,
            tenant_id=tenant.id,
            user_id=user.id,
            channel=NotificationChannel.INAPP,
            type=NotificationType.DOCUMENT_GENERATED,
            title="a",
            body="b",
            dedup_key=dedup,
        )
        await session.commit()
        assert first is not None
        assert second is not None
        assert first.id == second.id
