from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app.api import dependencies
from app.middleware.tenant import TenantMiddleware


def _request(path: str, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": headers or [],
        }
    )


@pytest.mark.asyncio
async def test_get_tenant_record_without_explicit_tenant_does_not_use_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail_fetch(_identifier: str):  # pragma: no cover - must not be called
        raise AssertionError("fallback lookup should be disabled for user requests")

    monkeypatch.setattr(dependencies, "_fetch_tenant_by_identifier", _fail_fetch)

    request = _request("/api/v1/auth/login")
    with pytest.raises(HTTPException) as exc_info:
        await dependencies.get_tenant_record(request)

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_auth_tenant_record_uses_verified_token_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = SimpleNamespace(slug="acme", id="acme-id")

    monkeypatch.setattr("app.core.security.verify_token", lambda token, expected_type: {"tenant": "acme"})

    async def _fetch(identifier: str):
        assert identifier == "acme"
        return tenant

    monkeypatch.setattr(dependencies, "_fetch_tenant_by_identifier", _fetch)

    request = _request(
        "/api/v1/auth/refresh",
        headers=[(b"authorization", b"Bearer valid-token")],
    )
    resolved = await dependencies.get_auth_tenant_record(request)
    assert resolved.slug == "acme"


@pytest.mark.asyncio
async def test_internal_fallback_allowed_only_for_explicit_test_scenarios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: SimpleNamespace(default_tenant_slug="public", app_env="test"),
    )
    async def _fetch(identifier: str):
        assert identifier == "test"
        return SimpleNamespace(slug="test")

    monkeypatch.setattr(dependencies, "_fetch_tenant_by_identifier", _fetch)

    request = _request("/api/v1/auth/login")
    request.state.allow_internal_tenant_fallback = True

    resolved = await dependencies.get_tenant_record(request)
    assert resolved.slug == "test"


@pytest.mark.asyncio
async def test_webhook_preload_ignores_query_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    middleware = TenantMiddleware(app=lambda scope, receive, send: None)  # type: ignore[arg-type]
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/webhooks/inbound/demo",
            "query_string": b"tenant=default",
            "headers": [],
        }
    )

    called = {"value": False}

    class _FakeSession:
        async def __aenter__(self):
            called["value"] = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("app.middleware.tenant.AsyncSessionLocal", lambda **kwargs: _FakeSession())
    await middleware._preload_webhook_tenant(request)

    assert called["value"] is False
    assert getattr(request.state, "tenant_record", None) is None
