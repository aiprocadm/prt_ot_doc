"""Minimal stub plugin to satisfy VSCode pytest runner."""

from __future__ import annotations

import os
import sys

import pytest

# Ensure lightweight in-memory defaults before the application imports settings.
os.environ.setdefault("APP_NAME", "TestService")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("REDIS_RESULT_URL", "redis://localhost:6379/15")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY", "test")
os.environ.setdefault("S3_SECRET_KEY", "test")
os.environ.setdefault("DEFAULT_LOCALE", "en-US")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)


def pytest_configure(config: pytest.Config) -> None:  # pragma: no cover - plugin hook
    """Hook for compatibility without altering behaviour."""
    # The real plugin injects markers and discovery tweaks. We only need
    # to exist so ``-p vscode_pytest`` imports cleanly in CI and local runs.
    # No-op keeps pytest behaviour unchanged while mirroring the interface.
    return None
