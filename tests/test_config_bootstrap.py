"""Tests for the configuration bootstrap process."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core import config


@pytest.fixture(autouse=True)
def _reset_config_caches() -> Iterator[None]:
    """Ensure settings caches are isolated between tests."""

    config.reset_settings_cache()
    try:
        yield
    finally:
        config.reset_settings_cache()


def test_bootstrap_without_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """bootstrap() should succeed when no .env file exists."""

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_NAME", raising=False)

    settings = config.bootstrap("api")

    assert settings.app_name == "prt-ot-doc"


def test_bootstrap_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated bootstrap() calls must avoid heavy side effects."""

    call_count = 0
    original_init = config.Settings.__init__

    def _counting_init(self: config.Settings, *args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(config.Settings, "__init__", _counting_init)

    first = config.bootstrap("api")
    second = config.bootstrap("api")

    assert first.model_dump() == second.model_dump()
    assert call_count == 2


def test_admin_bootstrap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Admin bootstrap env vars should be parsed without secrets in repo."""

    monkeypatch.setenv("ADMIN_BOOTSTRAP", "1")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@example.local")
    monkeypatch.setenv("ADMIN_PASSWORD", "temporary-password")
    monkeypatch.setenv("ADMIN_TENANT", "demo")

    settings = config.bootstrap("api")

    assert settings.admin_bootstrap is True
    assert settings.admin_email == "admin@example.local"
    assert settings.admin_password == "temporary-password"
    assert settings.admin_tenant == "demo"
