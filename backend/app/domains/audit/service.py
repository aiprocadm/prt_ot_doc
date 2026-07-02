"""Deprecated compat-shim — canonical location is :mod:`app.modules.audit.service` (ARCH-1)."""

from __future__ import annotations

from app.modules.audit.service import AuditDomainService  # noqa: F401  (compat re-export)

__all__ = ["AuditDomainService"]
