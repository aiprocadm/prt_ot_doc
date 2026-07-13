from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_ws_stub_returns_501(async_client, make_auth_headers):
    missing_tenant = await async_client.get("/ws/v1/events")
    assert missing_tenant.status_code == 400

    # Outbox event metadata is admin/owner-only (RBAC router sweep).
    headers = await make_auth_headers(tenant="test")
    response = await async_client.get("/ws/v1/events", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["transport_mode"] == "polling_fallback"
    assert payload["websocket_available"] is False
    assert payload["diagnostics"]["reason"] == "websocket_transport_pending"
