"""Minimal stub plugin to satisfy VSCode pytest runner."""

from __future__ import annotations

import pytest

from test_env_defaults import apply_test_env_defaults

# Ensure lightweight in-memory defaults before the application imports settings.
apply_test_env_defaults()


def pytest_configure(config: pytest.Config) -> None:  # pragma: no cover - plugin hook
    """Hook for compatibility without altering behaviour."""
    return None
