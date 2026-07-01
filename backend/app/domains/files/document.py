"""Deprecated compat-shim — canonical location is :mod:`app.modules.files.document` (ARCH-1)."""

from __future__ import annotations

from app.modules.files.document import DocumentService  # noqa: F401  (compat re-export)

__all__ = ["DocumentService"]
