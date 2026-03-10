from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.tenant import TENANT_HEADER, TenantMiddleware


async def _dummy_app(scope, receive, send):
    raise RuntimeError("ASGI app should not be called directly in tests")


@pytest.mark.asyncio
async def test_tenant_middleware_allows_system_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    def _unexpected(slug):
        raise AssertionError("tenant_required should not be called for system paths")

    monkeypatch.setattr("app.middleware.tenant.tenant_required", _unexpected)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [],
        "query_string": b"",
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert response.body == b"ok"


@pytest.mark.asyncio
async def test_tenant_middleware_requires_header_for_protected_paths() -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/protected",
        "headers": [],
        "query_string": b"",
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        await middleware.dispatch(request, call_next)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "TENANT_REQUIRED"


@pytest.mark.asyncio
async def test_tenant_middleware_passes_normalized_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    captured: dict[str, str] = {}

    valid_tenant = "Acme"

    def _fake_tenant_required(slug: str | None) -> SimpleNamespace:
        assert slug == valid_tenant
        captured["slug"] = slug or ""
        return SimpleNamespace(slug=valid_tenant)

    monkeypatch.setattr("app.middleware.tenant.tenant_required", _fake_tenant_required)

    class _FakeResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                id="tenant-id",
                slug="acme",
                code="acme",
                is_active=True,
                schema_name="tenant_acme",
                s3_prefix="tenants/acme",
                settings={},
            )

    class _FakeSession:
        def __init__(self) -> None:
            self._calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _query):
            self._calls += 1
            if self._calls == 1:
                return _FakeResult()

            class _EmptyResult:
                def scalar_one_or_none(self):
                    return None

            return _EmptyResult()

    monkeypatch.setattr("app.middleware.tenant.AsyncSessionLocal", lambda **kwargs: _FakeSession())

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/protected",
        "headers": [(TENANT_HEADER.encode(), b"Acme")],
        "query_string": b"",
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert captured["slug"] == "Acme"


@pytest.mark.asyncio
async def test_tenant_middleware_requires_header_for_similar_public_prefix() -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/publicity",
        "headers": [],
        "query_string": b"",
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    with pytest.raises(HTTPException) as exc_info:
        await middleware.dispatch(request, call_next)
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "TENANT_REQUIRED"


@pytest.mark.asyncio
async def test_tenant_middleware_allows_exact_public_prefix() -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/public/forms",
        "headers": [],
        "query_string": b"",
        "client": ("test", 0),
        "server": ("test", 80),
        "scheme": "http",
        "root_path": "",
    }
    request = Request(scope)

    response = await middleware.dispatch(request, call_next)
    assert response.status_code == 200
    assert response.body == b"ok"
