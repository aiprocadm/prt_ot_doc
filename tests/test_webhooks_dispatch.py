from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import get_settings
from app.services.webhooks import WebhookDispatcher


@pytest.mark.anyio
async def test_webhook_dispatcher_sends_exported_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_URLS_DOCUMENT_EXPORTED", "https://example.test/hooks/exported")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        destinations = dispatcher.resolve_destinations("DocumentExported")
        assert destinations
        await dispatcher.dispatch(
            event_type="DocumentExported",
            tenant_id="tenant-1",
            payload={"event_id": "evt-1", "zip_storage_key": "s3/key"},
            destination=destinations[0],
        )

    assert len(requests) == 1
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body["event_type"] == "DocumentExported"
    assert body["tenant_id"] == "tenant-1"
    assert requests[0].headers.get("Idempotency-Key") == "evt-1"

    get_settings.cache_clear()  # type: ignore[attr-defined]
