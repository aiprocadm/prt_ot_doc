from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_training_programs_requires_x_tenant(async_client) -> None:
    response = await async_client.get("/api/v1/training/programs", headers={"x-tenant": ""})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "TENANT_REQUIRED"
