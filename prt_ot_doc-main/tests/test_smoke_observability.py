import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_metrics_endpoint_exposes_prometheus(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
