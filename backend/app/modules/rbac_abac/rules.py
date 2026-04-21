"""Compatibility re-export for RBAC/ABAC permission vocabulary.

Single source of truth lives in :mod:`app.core.rbac_abac`.
"""

from app.core.rbac_abac import RESOURCE_PERMISSIONS, ROLE_ALIASES, ROLE_PERMISSIONS

__all__ = ["RESOURCE_PERMISSIONS", "ROLE_ALIASES", "ROLE_PERMISSIONS"]
