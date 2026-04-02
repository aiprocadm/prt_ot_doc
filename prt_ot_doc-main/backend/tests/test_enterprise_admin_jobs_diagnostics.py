from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.api.routes.admin_authz import get_provider_status, get_tenant_health
from app.api.routes.jobs import get_queue_summary, list_failed_jobs, list_poisoned_events


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _OneResult:
    def __init__(self, value):
        self._value = value

    def one(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return self._values


class _AllResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _SequenceSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("Unexpected extra execute() call")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_provider_status_exposes_blocking_non_production_providers() -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", is_active=True)

    payload = await get_provider_status(_=None, tenant=tenant)

    assert payload.production_ready is False
    assert payload.blocking_for_golive
    assert any(item.mode == "non_production" for item in payload.providers)


@pytest.mark.asyncio
async def test_tenant_health_aggregates_jobs_outbox_and_provider_risk() -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", is_active=True)
    session = _SequenceSession(
        [
            _ScalarResult(2),
            _OneResult((8, 3)),
            _ScalarResult(1),
        ]
    )

    payload = await get_tenant_health(_=None, tenant=tenant, session=session)

    assert payload.failed_jobs_last24h == 2
    assert payload.outbox_pending == 8
    assert payload.outbox_failed == 3
    assert payload.outbox_events_poisoned == 1
    assert payload.score < 100
    assert payload.recommendations


@pytest.mark.asyncio
async def test_queue_summary_reports_current_and_recent_statuses() -> None:
    tenant = SimpleNamespace(id="tenant-1")
    session = _SequenceSession(
        [
            _AllResult([
                ("queued", 5),
                ("running", 2),
                ("failed", 4),
                ("canceled", 1),
                ("success", 12),
            ]),
            _ScalarResult(3),
            _ScalarResult(11),
        ]
    )

    payload = await get_queue_summary(session=session, tenant=tenant, __=None)

    assert payload.queued == 5
    assert payload.running == 2
    assert payload.failed_total == 4
    assert payload.failed_last24h == 3
    assert payload.success_last24h == 11


@pytest.mark.asyncio
async def test_failed_jobs_endpoint_returns_items_with_context() -> None:
    now = datetime.now(timezone.utc)
    tenant = SimpleNamespace(id="tenant-1")
    rows = [
        SimpleNamespace(
            id="job-1",
            kind="doc",
            error_code="E_PIPELINE",
            error_payload={"detail": "failure"},
            started_at=now,
            ended_at=now,
            correlation_id="cid-1",
        )
    ]
    session = _SequenceSession([_ScalarResult(1), _ScalarsResult(rows)])

    payload = await list_failed_jobs(limit=50, offset=0, session=session, tenant=tenant, __=None)

    assert payload.total == 1
    assert payload.items[0].id == "job-1"
    assert payload.items[0].error_code == "E_PIPELINE"


@pytest.mark.asyncio
async def test_poisoned_events_endpoint_returns_items() -> None:
    now = datetime.now(timezone.utc)
    tenant = SimpleNamespace(id="tenant-1")
    rows = [
        SimpleNamespace(
            id="evt-1",
            event_type="approval.created",
            attempts=7,
            last_error="poisoned",
            created_at=now,
            next_attempt_at=None,
        )
    ]
    session = _SequenceSession([_ScalarResult(1), _ScalarsResult(rows)])

    payload = await list_poisoned_events(limit=50, offset=0, session=session, tenant=tenant, __=None)

    assert payload.total == 1
    assert payload.items[0].event_type == "approval.created"
