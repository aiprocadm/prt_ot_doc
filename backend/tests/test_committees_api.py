"""API-contract tests for committees routes (P10-01), mocking session.

Follows the repo convention (see test_work_permit_electrical_groups_api.py):
patch the route module's session/query helpers with AsyncMock — no live DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes
from app.models.committees import MeetingStatus
from app.schemas.committees import DecisionCreate, MeetingStatusUpdate


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1")


def _meeting(status=MeetingStatus.PLANNED):
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="m1",
        committee_id="c1",
        tenant_id="tenant-1",
        scheduled_at=now,
        location=None,
        status=status,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


@pytest.mark.asyncio
async def test_transition_meeting_rejects_illegal(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD))
    )
    with pytest.raises(Exception) as exc:
        await routes.update_meeting(
            mid="m1",
            payload=MeetingStatusUpdate(status=MeetingStatus.PLANNED),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_add_decision_requires_held(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED))
    )
    with pytest.raises(Exception) as exc:
        await routes.create_decision(
            mid="m1",
            payload=DecisionCreate(text="x"),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409
