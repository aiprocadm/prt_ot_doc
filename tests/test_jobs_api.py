from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_job_status_endpoint_for_unknown_job(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    transport = ASGITransport(app=app_fixture)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/jobs/unknown", headers=headers)

    assert response.status_code == 404
