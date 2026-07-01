"""Deprecated compat-shim — canonical location is :mod:`app.modules.contractors.documents` (ARCH-1)."""

from __future__ import annotations

from app.modules.contractors.documents import (  # noqa: F401  (compat re-export)
    best_document,
    document_expiry_status,
    requirement_status,
)

__all__ = ["document_expiry_status", "best_document", "requirement_status"]
