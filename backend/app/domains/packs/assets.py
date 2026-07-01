"""Deprecated compat-shim — canonical location is :mod:`app.modules.packs.assets` (ARCH-1)."""

from __future__ import annotations

from app.modules.packs.assets import (  # noqa: F401  (compat re-export)
    DEFAULT_LOGO_BYTES,
    DEFAULT_STAMP_BYTES,
    InlineImageDescriptor,
    build_inline_image_descriptor,
)

__all__ = [
    "DEFAULT_LOGO_BYTES",
    "DEFAULT_STAMP_BYTES",
    "InlineImageDescriptor",
    "build_inline_image_descriptor",
]
