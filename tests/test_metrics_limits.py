from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status

from app.api.app import create_app


@pytest.mark.asyncio()
async def test_request_body_limit_enforced(async_client):
    too_large_payload = "x" * (1_048_576 + 1024)
    response = await async_client.post(
        "/api/v1/auth/login",
        content=too_large_payload,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    body = response.json()
    assert body["code"] == "PAYLOAD_TOO_LARGE"
    assert body["error_code"] == "PAYLOAD_TOO_LARGE"
    assert "payload" in body["message"].lower()
    assert body["details"]["limit"] == 1_048_576
    assert body["trace_id"] == response.headers["X-Trace-Id"]
    assert body["request_id"] == body["trace_id"]

    valid_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "secret"},
        headers={"X-Tenant": "test"},
    )
    assert valid_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert "trace_id" in valid_response.json()


@pytest.mark.asyncio()
async def test_metrics_endpoint_reports_http_latency_and_errors(async_client, app_fixture):
    app_fixture.state.redis_client.lengths["default"] = 3

    ok_response = await async_client.get("/health")
    assert ok_response.status_code == status.HTTP_200_OK

    error_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "absent@example.com", "password": "bad"},
        headers={"X-Tenant": "test"},
    )
    assert error_response.status_code == status.HTTP_401_UNAUTHORIZED

    metrics_response = await async_client.get("/metrics")
    assert metrics_response.status_code == status.HTTP_200_OK

    metrics_payload = metrics_response.text
    assert "http_request_latency_p95_seconds" in metrics_payload
    assert 'path="/health"' in metrics_payload
    assert "http_request_errors_total" in metrics_payload
    assert 'status="4xx"' in metrics_payload
    assert "pipeline_requests_total" in metrics_payload
    assert "pipeline_stage_duration_seconds" in metrics_payload
    assert "pipeline_total_duration_seconds" in metrics_payload
    assert "celery_task_latency_p95_seconds" in metrics_payload
    assert 'celery_queue_depth{queue="default"}' in metrics_payload


@pytest.mark.asyncio()
async def test_metrics_endpoint_respects_feature_flag(monkeypatch):
    monkeypatch.setenv("ENABLE_METRICS", "0")

    app = create_app()

    class _StubRedis:
        async def ping(self) -> bool:
            return True

        async def llen(self, key: str) -> int:
            return 0

    app.state.redis_client = _StubRedis()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/metrics")
    assert response.status_code == status.HTTP_404_NOT_FOUND
