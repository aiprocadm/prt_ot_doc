"""Shared defaults for pytest/VS Code discovery without external services."""

from __future__ import annotations

import os
import sys


def apply_test_env_defaults() -> None:
    """Set lightweight defaults before importing app settings during tests."""

    os.environ.setdefault("APP_NAME", "TestService")
    os.environ["APP_TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"
    os.environ.setdefault("APP_RUN_MODE", "docker")
    os.environ.setdefault("CELERY_EAGER", "false")
    os.environ.setdefault("ENABLE_METRICS", "true")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("REDIS_URL", "memory://")
    os.environ.setdefault("REDIS_RESULT_URL", "cache+memory://")
    os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
    os.environ.setdefault("STORAGE_BACKEND", "local")
    os.environ.setdefault("S3_BACKEND", "local")
    os.environ.setdefault("STORAGE_ROOT", "./.local_storage")
    os.environ.setdefault("S3_ENDPOINT", "http://localhost")
    os.environ.setdefault("S3_BUCKET", "test-bucket")
    os.environ.setdefault("S3_ACCESS_KEY", "test")
    os.environ.setdefault("S3_SECRET_KEY", "test")
    os.environ.setdefault("DEFAULT_LOCALE", "en-US")
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)
    # Прод-дефолт 15s на медленных машинах (одноядерный VPS под полным прогоном)
    # даёт ложные 504 GATEWAY_TIMEOUT в случайных API-тестах; сами таймауты
    # тестируются точечными monkeypatch.setenv (см. test_files_upload.py).
    os.environ.setdefault("REQUEST_TIMEOUT_SECONDS", "120")
