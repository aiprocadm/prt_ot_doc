from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.routes.ws_stub import ws_events_stub


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Result(self._rows)


async def test_ws_stub_returns_polling_fallback_payload() -> None:
    rows = [
        SimpleNamespace(
            id="evt-1",
            event_type="approval.started",
            status="pending",
            destination="internal://approval",
            attempts=1,
            created_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
            payload={"event_id": "e-1", "tenant_id": "t-1"},
        )
    ]
    session = _Session(rows)
    tenant = SimpleNamespace(id="tenant-1")

    payload = await ws_events_stub(session=session, tenant=tenant, limit=50, since=None)

    assert payload.transport_mode == "polling_fallback"
    assert payload.provider_mode == "non_production"
    assert payload.websocket_available is False
    assert payload.count == 1
    assert payload.items[0].id == "evt-1"
    assert payload.items[0].event_type == "approval.started"
    assert payload.items[0].payload_keys == ["event_id", "tenant_id"]


async def test_ws_stub_returns_empty_items_when_no_events() -> None:
    session = _Session([])
    tenant = SimpleNamespace(id="tenant-1")

    payload = await ws_events_stub(session=session, tenant=tenant, limit=20, since=None)

    assert payload.transport_mode == "polling_fallback"
    assert payload.count == 0
    assert payload.items == []
