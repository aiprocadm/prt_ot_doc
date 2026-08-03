"""OPS-73 срез-3: батч-рекордер обращений к устаревшим поверхностям.

Пишет в БД не на каждый запрос, а порциями: ``note_deprecated_hit`` копит
в памяти, ``drain_pending`` сливает накопленное упсертами. Троттлинг — защита
БД от write-амплификации, а не точность: счётчик может отставать на интервал
слива, и это осознанно.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import api_deprecation_recorder as rec
from app.services.api_deprecation_usage import usages_to_notify

_NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _clean_state():
    rec.reset_for_tests()
    yield
    rec.reset_for_tests()


@pytest.mark.asyncio
async def test_notes_accumulate_and_drain_writes_upserts(sessionmaker):
    rec.note_deprecated_hit("demo", "/api/v1/files-legacy")
    rec.note_deprecated_hit("demo", "/api/v1/files-legacy")
    rec.note_deprecated_hit("other", "/api/v1/files-legacy")

    async with sessionmaker() as session:
        written = await rec.drain_pending(session, now=_NOW)
        await session.commit()
        assert written == 2  # две пары (tenant, prefix)
        rows = await usages_to_notify(session, now=_NOW)
    by_slug = {r.tenant_slug: r.hits_2xx for r in rows}
    assert by_slug == {"demo": 2, "other": 1}


@pytest.mark.asyncio
async def test_drain_on_empty_is_noop(sessionmaker):
    async with sessionmaker() as session:
        assert await rec.drain_pending(session, now=_NOW) == 0


def test_note_schedules_background_flush_once(monkeypatch):
    """Планируется не больше одного отложенного слива на порцию."""
    scheduled: list[int] = []
    monkeypatch.setattr(rec, "_schedule_flush", lambda: scheduled.append(1))
    rec.note_deprecated_hit("demo", "/api/v1/files-legacy")
    rec.note_deprecated_hit("demo", "/api/v1/files-legacy")
    rec.note_deprecated_hit("b", "/api/v1/files-legacy")
    assert len(scheduled) == 1
