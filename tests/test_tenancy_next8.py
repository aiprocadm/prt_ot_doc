from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kombu import Queue

from app.domains.files.utils import build_storage_key
from app.services import celery_app as celery_app_module
from app.services.celery_app import route_task_by_tenant


@pytest.mark.anyio
async def test_missing_xtenant_returns_400(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    headers.pop("x-tenant", None)
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/tenants", headers=headers)
    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "TENANT_REQUIRED"


def test_s3_prefix_uses_tenant_namespace() -> None:
    key = build_storage_key(tenant_slug="tenant-123", sha256_hex="a" * 64, extension="pdf")
    assert key.startswith("tenants/tenant-123/")


def test_celery_route_falls_back_to_default_when_tenant_queue_not_registered() -> None:
    """Per-tenant queues only work when declared in task_queues and consumed by workers."""
    route = route_task_by_tenant("documents.generate", [], {"tenant_id": "abc"}, {})
    assert route is None


def test_celery_route_uses_tenant_queue_when_registered() -> None:
    app = celery_app_module.celery_app
    original = tuple(app.conf.task_queues)
    try:
        app.conf.task_queues = original + (Queue("tenant.abc", routing_key="tenant.abc"),)
        route = route_task_by_tenant("documents.generate", [], {"tenant_id": "abc"}, {})
        assert route is not None
        assert route["queue"] == "tenant.abc"
    finally:
        app.conf.task_queues = original


def test_celery_route_requires_tenant_for_business_tasks() -> None:
    with pytest.raises(ValueError):
        route_task_by_tenant("documents.generate", [], {}, {})
