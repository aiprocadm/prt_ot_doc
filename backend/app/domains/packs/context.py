"""Deprecated compat-shim — canonical location is :mod:`app.modules.packs.context` (ARCH-1)."""

from __future__ import annotations

from app.modules.packs.context import enrich_context  # noqa: F401  (compat re-export)

__all__ = ["enrich_context"]
