"""Contract: generated OpenAPI from FastAPI matches expected API surface shape."""

from __future__ import annotations

import sys

import pytest

from app.api.app import create_app
from app.core.config import Settings


@pytest.mark.contract
def test_generated_openapi_exposes_v1_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "development",
            "SECRET_KEY": "test-secret-key-32chars-minimum!!",
            "LIBREOFFICE_BIN": sys.executable,
            "ENABLE_OPENAPI_DOCS": True,
            "ENABLE_METRICS": False,
        }
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: settings)
    app = create_app(settings)
    schema = app.openapi()
    paths = schema.get("paths") or {}
    assert isinstance(paths, dict) and paths
    v1_paths = [p for p in paths if p.startswith("/api/v1/")]
    assert v1_paths, "expected at least one path under /api/v1/ in generated OpenAPI"
