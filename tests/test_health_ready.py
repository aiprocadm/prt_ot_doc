import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_health_returns_ok(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_ready_reports_success(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert isinstance(body["redis"], bool)
    if "redis_skipped" in body:
        assert body["redis"] is True
        assert body["redis_skipped"] is True


@pytest.mark.anyio
async def test_ready_returns_service_unavailable_when_checks_fail(app_fixture, monkeypatch) -> None:
    async def failing_postgres(_: FastAPI) -> None:
        raise RuntimeError("database offline")

    monkeypatch.setattr("app.api.routes.health._ping_postgres", failing_postgres)

    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["redis"] is True
