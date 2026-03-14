from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_ws_stub_returns_501(async_client):
    missing_tenant = await async_client.get("/ws/v1/events")
    assert missing_tenant.status_code == 400

    response = await async_client.get("/ws/v1/events", headers={"X-Tenant": "test"})
    assert response.status_code == 501
