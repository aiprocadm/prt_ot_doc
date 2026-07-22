"""Integration tests: the SSRF guard blocks unsafe webhook targets at dispatch time
(SEC-64 §64.3).

Runs in the default test env (``app_env="development"``). A *literal* private IP is
rejected in every environment, so these tests need no production config and no
network — the guard blocks before the mock transport is ever hit.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import get_settings
from app.services.webhooks import WebhookDispatcher, WebhookDispatchError


def _recording_client() -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


@pytest.mark.anyio
async def test_dispatch_blocks_private_ip_before_send() -> None:
    client, requests = _recording_client()
    async with client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        with pytest.raises(WebhookDispatchError) as excinfo:
            await dispatcher.dispatch(
                event_type="DocumentExported",
                tenant_id="tenant-1",
                payload={"event_id": "evt-1"},
                destination="https://10.0.0.5/hook",  # private A — SSRF target
            )
    # Blocked pre-flight: sentinel status 0, and no request ever left the process.
    assert excinfo.value.status_code == 0
    assert requests == []


@pytest.mark.anyio
async def test_dispatch_blocks_cloud_metadata_before_send() -> None:
    client, requests = _recording_client()
    async with client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        with pytest.raises(WebhookDispatchError):
            await dispatcher.dispatch(
                event_type="DocumentExported",
                tenant_id="tenant-1",
                payload={"event_id": "evt-1"},
                destination="https://169.254.169.254/latest/meta-data/",
            )
    assert requests == []


@pytest.mark.anyio
async def test_dispatch_allows_safe_host() -> None:
    client, requests = _recording_client()
    async with client:
        dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
        await dispatcher.dispatch(
            event_type="DocumentExported",
            tenant_id="tenant-1",
            payload={"event_id": "evt-1"},
            destination="https://example.test/hooks",  # dev-permissive fake host
        )
    assert len(requests) == 1


@pytest.mark.anyio
async def test_kill_switch_disables_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBHOOK_SSRF_GUARD_ENABLED", "false")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        client, requests = _recording_client()
        async with client:
            dispatcher = WebhookDispatcher(settings=get_settings(), client=client)
            # Guard off: even a private IP is attempted (mock returns 204 → no failure).
            await dispatcher.dispatch(
                event_type="DocumentExported",
                tenant_id="tenant-1",
                payload={"event_id": "evt-1"},
                destination="https://10.0.0.5/hook",
            )
        assert len(requests) == 1
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]
