from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_outbox_events_route_not_shadowed_by_dynamic_id(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/admin/outbox/events", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
