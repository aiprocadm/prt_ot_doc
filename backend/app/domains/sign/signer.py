"""Deprecated compat-shim — canonical location is :mod:`app.modules.sign.signer` (ARCH-1)."""

from __future__ import annotations

from app.modules.sign.signer import DocumentSigner  # noqa: F401  (compat re-export)

__all__ = ["DocumentSigner"]
