from __future__ import annotations

import sys

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.app import _normalize_patterns, create_app
from app.core.config import Settings
from app.middleware.tenant import TenantMiddleware


def test_normalize_patterns_handles_wildcards() -> None:
    assert _normalize_patterns(["   example.com  ", "", "*.test"]) == ["example.com", "*.test"]
    assert _normalize_patterns(["*", "example.com"]) == ["*"]


@pytest.mark.anyio
async def test_create_app_configures_middlewares_and_routes() -> None:
    settings = Settings.model_validate(
        {
            "APP_NAME": "Docs",
            "API_PREFIX": "/api",
            "API_V1_PREFIX": "/api/v1",
            "APP_TRUSTED_HOSTS": ["example.com", " api.test "],
            "APP_CORS_ORIGINS": ["https://frontend.local"],
            "ENABLE_METRICS": True,
            "LIBREOFFICE_BIN": sys.executable,
            "SECRET_KEY": "super-secret",
        }
    )

    app = create_app(settings)
    assert isinstance(app, FastAPI)
    assert app.title == "Docs"
    assert app.docs_url == "/api/docs"
    assert app.openapi_url == "/api/openapi.json"
    assert app.state.settings is settings
    assert app.state.debug is settings.debug

    middleware_classes = {middleware.cls for middleware in app.user_middleware}
    assert TrustedHostMiddleware in middleware_classes
    assert CORSMiddleware in middleware_classes
    assert TenantMiddleware in middleware_classes

    cors_middleware = next(m for m in app.user_middleware if m.cls is CORSMiddleware)
    assert cors_middleware.kwargs["allow_origins"] == ["https://frontend.local"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://example.com") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        ready = await client.get("/ready")
        if ready.status_code == 200:
            body = ready.json()
            assert body["status"] == "ok"
            assert body["postgres"] is True
            assert isinstance(body["redis"], bool)
            if "redis_skipped" in body:
                assert body["redis"] is True
                assert body["redis_skipped"] is True
        else:
            assert ready.status_code == 503
            body = ready.json()
            assert body["status"] == "degraded"
            assert isinstance(body["postgres"], bool)
            assert isinstance(body["redis"], bool)
        metrics = await client.get("/metrics")
        assert metrics.status_code == 200
        assert metrics.headers["content-type"].startswith("text/plain")

    # Ensure router from v1 is registered by checking one known route prefix.
    assert any(route.path.startswith(settings.api_v1_prefix) for route in app.routes)
