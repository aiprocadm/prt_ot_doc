from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_ws_stub_returns_501(async_client):
    response = await async_client.get("/ws/v1/events")
    assert response.status_code == 501
