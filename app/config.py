"""Application configuration helpers for legacy imports."""

from __future__ import annotations

from typing import Any

from .core.config import Settings, bootstrap, get_settings

__all__ = ["Settings", "get_settings", "bootstrap", "settings_dict"]


def settings_dict() -> dict[str, Any]:
    """Expose current settings as a plain dictionary."""

    settings = get_settings()
    return settings.model_dump()
