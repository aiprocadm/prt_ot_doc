"""OpenAPI/Swagger URL alignment, tenant middleware bypass, production policy."""

from __future__ import annotations

import sys

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.app import create_app
from app.core.config import DEV_PRIVATE_KEY, DEV_PUBLIC_KEY, Settings

_PRODUCTION_LIKE: dict[str, object] = {
    "APP_ENV": "production",
    "SECRET_KEY": "not-the-default-staging-secret-key-32chars!!",
    "POSTGRES_PASSWORD": "staging-postgres-secret-not-default",
    "S3_ACCESS_KEY": "staging-access-not-prt-local",
    "S3_SECRET_KEY": "staging-secret-not-prt-local",
    "S3_BACKEND": "minio",
    "PRIVATE_KEY_PEM": DEV_PRIVATE_KEY,
    "PUBLIC_KEY_PEM": DEV_PUBLIC_KEY,
    "LIBREOFFICE_BIN": sys.executable,
    "ENABLE_OPENAPI_DOCS": True,
    "ENABLE_METRICS": False,
}


def test_production_disables_openapi_docs_even_when_env_requests_true() -> None:
    settings = Settings.model_validate(_PRODUCTION_LIKE)
    assert settings.enable_openapi_docs is False


@pytest.mark.anyio
async def test_production_create_app_exposes_no_openapi_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_validate(_PRODUCTION_LIKE)
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app(settings)
    assert app.docs_url is None
    assert app.openapi_url is None
    assert app.redoc_url is None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/api/docs")
        assert docs.status_code == 404
        spec = await client.get("/api/openapi.json")
        assert spec.status_code == 404


@pytest.mark.anyio
async def test_openapi_ui_reachable_without_x_tenant_when_docs_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "API_PREFIX": "/api",
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LIBREOFFICE_BIN": sys.executable,
            "ENABLE_OPENAPI_DOCS": True,
            "ENABLE_METRICS": False,
        }
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app(settings)
    assert app.docs_url == "/api/docs"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        docs = await client.get("/api/docs")
        assert docs.status_code == 200
        spec = await client.get("/api/openapi.json")
        assert spec.status_code == 200
