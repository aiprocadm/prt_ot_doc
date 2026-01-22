from __future__ import annotations

from pathlib import Path

import pytest

from app.core import config


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> None:
    config.reset_settings_cache()
    yield
    config.reset_settings_cache()


def test_split_csv_handles_various_inputs() -> None:
    assert config.split_csv(None, default=["alpha"]) == ["alpha"]
    assert config.split_csv(" a, b ,, c ", default=[]) == ["a", "b", "c"]
    assert config.split_csv(["foo", "", "bar"], default=["noop"]) == ["foo", "bar"]


def test_split_csv_rejects_non_iterable() -> None:
    class NotIterable:
        __slots__ = ()

    with pytest.raises(TypeError):
        config.split_csv(NotIterable(), default=["noop"])  # type: ignore[arg-type]


def test_binary_exists_with_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    binary = tmp_path / "custom" / "bin"
    binary.parent.mkdir()
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)

    assert config.binary_exists(str(binary))
    assert config.binary_exists(str(binary.parent)) is True  # directory exists
    assert config.binary_exists(str(tmp_path / "missing")) is False

    # Ensure PATH lookup is honoured when candidate has no path separators.
    path_binary = tmp_path / "bin"
    path_binary.write_text("#!/bin/sh\n")
    path_binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert config.binary_exists("bin") is True


def test_settings_normalization_and_validators(tmp_path: Path) -> None:
    # Ensure libreoffice validator accepts the temporary executable.
    executable = tmp_path / "soffice"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)

    settings = config.Settings.model_validate(
        {
            "APP_NAME": "DocService",
            "APP_TRUSTED_HOSTS": "api.example.com,  example.org",
            "APP_CORS_ORIGINS": ("https://one.test", "https://two.test"),
            "WORKER_QUEUES": "alpha, beta",
            "LIBREOFFICE_BIN": str(executable),
            "DEFAULT_TENANT_SLUG": "Acme-Co",
            "SHARED_SCHEMA": "shared_schema",
        }
    )

    assert settings.allowed_hosts == ["api.example.com", "example.org"]
    assert settings.allowed_origins == ["https://one.test", "https://two.test"]
    assert settings.worker_queues == ["alpha", "beta", settings.pdf_worker_queue]
    assert settings.libreoffice_bin == str(executable)
    assert settings.default_tenant_slug == "acme-co"
    assert settings.shared_schema == "shared_schema"
    assert settings.celery.worker_queues == settings.worker_queues
    assert settings.celery.pdf_queue == settings.pdf_worker_queue
    assert settings.runtime.environment == "development"
    assert settings.runtime.is_development is True


def test_settings_default_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = config.Settings.model_validate(
        {
            "POSTGRES_HOST": "db",
            "POSTGRES_PORT": 5432,
            "POSTGRES_DB": "docs",
            "POSTGRES_USER": "svc",
            "POSTGRES_PASSWORD": "secret",
            "LIBREOFFICE_BIN": "python",
        }
    )

    assert settings.database_url == "postgresql+asyncpg://svc:secret@db:5432/docs"
    assert settings.database.url == settings.database_url
    assert settings.database.alembic_url.endswith("docs")


def test_redis_section_reflects_broker_and_result_urls() -> None:
    settings = config.Settings.model_validate(
        {
            "REDIS_URL": "redis://cache:6379/0",
            "REDIS_RESULT_URL": "redis://cache:6380/1",
            "LIBREOFFICE_BIN": "python",
        }
    )

    assert settings.redis.broker_url == "redis://cache:6379/0"
    assert settings.redis.result_url == "redis://cache:6380/1"
    assert settings.redis.has_dedicated_result_backend is True
