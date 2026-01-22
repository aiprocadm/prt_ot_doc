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


@pytest.mark.asyncio
async def test_tenant_middleware_passes_normalized_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = TenantMiddleware(_dummy_app)

    async def call_next(request: Request) -> Response:
        return Response(content=b"ok")

    captured: dict[str, str] = {}

    def _fake_tenant_required(slug: str | None) -> SimpleNamespace:
        assert slug == "Acme"
        captured["slug"] = slug or ""
        return SimpleNamespace(slug="acme")

    monkeypatch.setattr("app.middleware.tenant.tenant_required", _fake_tenant_required)

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
