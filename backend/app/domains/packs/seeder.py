"""Deprecated compat-shim — canonical location is :mod:`app.modules.packs.seeder` (ARCH-1)."""

from __future__ import annotations

from app.modules.packs.seeder import (  # noqa: F401  (compat re-export)
    ensure_default_packs,
    ensure_pack_by_code,
)

__all__ = ["ensure_default_packs", "ensure_pack_by_code"]
