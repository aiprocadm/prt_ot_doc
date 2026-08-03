"""OPS-73 срез-3 — уведомления потребителям устаревших API (outbox-событие)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.models import Outbox, Tenant
from app.services.api_deprecation_notify import notify_deprecated_usages
from app.services.api_deprecation_usage import record_hit
from app.services.events import EventType

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


async def _seed_tenant(session, slug="demo"):
    t = Tenant(slug=slug, name=slug, contact_email=f"{slug}@example.com")
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_notify_enqueues_outbox_event_and_marks_row(sessionmaker):
    async with sessionmaker() as session:
        tenant = await _seed_tenant(session)
        row = await record_hit(
            session, tenant_slug="demo", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        await session.commit()

        notified = await notify_deprecated_usages(session, now=_NOW)
        await session.commit()
        assert notified == 1
        assert row.last_notified_at == _NOW

        events = (
            (await session.execute(select(Outbox).where(Outbox.tenant_id == tenant.id)))
            .scalars()
            .all()
        )
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == EventType.API_DEPRECATION_NOTICE.value
    assert ev.payload["path_prefix"] == "/api/v1/files-legacy"
    assert ev.payload["successor"] == "/api/v1/files"
    assert ev.payload["sunset"] == "2027-07-30"
    assert ev.payload["hits_2xx"] == 1


@pytest.mark.asyncio
async def test_notify_skips_unknown_slug_but_marks_it(sessionmaker):
    """Слуг без арендатора (сканер/опечатка): уведомлять некого, но строку
    помечаем — иначе она выбиралась бы каждым тиком вечно."""
    async with sessionmaker() as session:
        await record_hit(
            session, tenant_slug="ghost", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        await session.commit()
        notified = await notify_deprecated_usages(session, now=_NOW)
        await session.commit()
        assert notified == 0
        outbox_count = len(((await session.execute(select(Outbox))).scalars().all()))
        assert outbox_count == 0
        # повторный тик не выбирает строку снова
        assert await notify_deprecated_usages(session, now=_NOW + timedelta(hours=1)) == 0


@pytest.mark.asyncio
async def test_notify_respects_min_interval(sessionmaker):
    async with sessionmaker() as session:
        await _seed_tenant(session)
        await record_hit(session, tenant_slug="demo", path_prefix="/api/v1/files-legacy", when=_NOW)
        await session.commit()
        assert await notify_deprecated_usages(session, now=_NOW) == 1
        # через день — тихо; тот же арендатор не бомбардируется
        assert await notify_deprecated_usages(session, now=_NOW + timedelta(days=1)) == 0


@pytest.mark.asyncio
async def test_notify_prefix_gone_from_registry_marks_without_event(sessionmaker):
    async with sessionmaker() as session:
        await _seed_tenant(session)
        await record_hit(
            session, tenant_slug="demo", path_prefix="/api/v1/no-longer-listed", when=_NOW
        )
        await session.commit()
        assert await notify_deprecated_usages(session, now=_NOW) == 0
        assert len(((await session.execute(select(Outbox))).scalars().all())) == 0
