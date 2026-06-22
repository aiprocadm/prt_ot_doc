from __future__ import annotations

import hmac
import json
from hashlib import sha256

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.models import Tenant, WebhookEndpoint
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
    assert body["type"] == "DocumentExported"
    assert body["id"] == "evt-1"
    assert requests[0].headers.get("Idempotency-Key") == "evt-1"

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_webhook_signature_is_valid(sessionmaker) -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = WebhookEndpoint(
            tenant_id=tenant.id,
            name="exported",
            url="https://example.test/hooks/exported",
            headers={},
            secret="top-secret",
            is_enabled=True,
            subscribed_events=["DocumentExported"],
        )
        session.add(endpoint)
        await session.commit()

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        async with sessionmaker() as session:
            await dispatcher.dispatch(
                event_type="DocumentExported",
                tenant_id=str(tenant.id),
                payload={"event_id": "evt-1", "zip_storage_key": "s3/key"},
                session=session,
            )

    assert len(requests) == 1
    timestamp = requests[0].headers.get("X-Timestamp")
    signature = requests[0].headers.get("X-Signature")
    assert signature is not None
    assert timestamp is not None
    expected = hmac.new(
        b"top-secret", f"{timestamp}.".encode("utf-8") + requests[0].content, sha256
    ).hexdigest()
    assert signature == f"v1={expected}"
