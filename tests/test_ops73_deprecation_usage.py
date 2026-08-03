"""OPS-73 срез-3 — персистентный учёт использования устаревших API + выборка для уведомлений."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.api_deprecation_usage import (
    record_hit,
    usages_to_notify,
)

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_record_hit_upserts_and_accumulates(sessionmaker):
    async with sessionmaker() as session:
        row = await record_hit(
            session, tenant_slug="demo", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        assert row.hits_2xx == 1
        assert row.first_seen_at == _NOW
        later = _NOW + timedelta(hours=2)
        row = await record_hit(
            session, tenant_slug="demo", path_prefix="/api/v1/files-legacy", when=later, hits=3
        )
        await session.commit()
        assert row.hits_2xx == 4
        assert row.first_seen_at == _NOW
        assert row.last_seen_at == later


@pytest.mark.asyncio
async def test_record_hit_separates_tenants_and_prefixes(sessionmaker):
    async with sessionmaker() as session:
        await record_hit(session, tenant_slug="a", path_prefix="/api/v1/files-legacy", when=_NOW)
        await record_hit(session, tenant_slug="b", path_prefix="/api/v1/files-legacy", when=_NOW)
        await record_hit(session, tenant_slug="a", path_prefix="/api/v1/other-old", when=_NOW)
        await session.commit()
        rows = await usages_to_notify(session, now=_NOW)
        assert len(rows) == 3


@pytest.mark.asyncio
async def test_usages_to_notify_selection_rules(sessionmaker):
    """Уведомляем: активные за окно и не уведомлённые за интервал."""
    async with sessionmaker() as session:
        fresh = await record_hit(
            session, tenant_slug="fresh", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        stale = await record_hit(
            session,
            tenant_slug="stale",
            path_prefix="/api/v1/files-legacy",
            when=_NOW - timedelta(days=90),
        )
        recently_notified = await record_hit(
            session, tenant_slug="told", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        recently_notified.last_notified_at = _NOW - timedelta(days=5)
        long_ago_notified = await record_hit(
            session, tenant_slug="told-long-ago", path_prefix="/api/v1/files-legacy", when=_NOW
        )
        long_ago_notified.last_notified_at = _NOW - timedelta(days=45)
        await session.commit()

        rows = await usages_to_notify(session, now=_NOW)
        slugs = sorted(r.tenant_slug for r in rows)
    # stale — активности нет 90 дней (не тревожим); told — уведомлён 5 дней назад.
    assert slugs == ["fresh", "told-long-ago"]
    assert fresh.id != stale.id
