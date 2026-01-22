"""Minimal stub plugin to satisfy VSCode pytest runner."""

from __future__ import annotations

import os

import pytest

# Ensure lightweight in-memory defaults before the application imports settings.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "memory://")
os.environ.setdefault("APP_ENV", "test")


def pytest_configure(config: pytest.Config) -> None:  # pragma: no cover - plugin hook
    """Hook for compatibility without altering behaviour."""
    # The real plugin injects markers and discovery tweaks. We only need
    # to exist so ``-p vscode_pytest`` imports cleanly in CI and local runs.
    # No-op keeps pytest behaviour unchanged while mirroring the interface.
    return None
