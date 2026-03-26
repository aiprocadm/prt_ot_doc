"""Progressive compatibility layer for tenant-related ORM models.

This module is part of the staged decomposition of ``app.models.models``.
It intentionally re-exports canonical tenant entities without changing the
underlying table declarations yet, which keeps Alembic/import compatibility
stable while allowing new code to stop depending on the mega-module.
"""

from app.models.models import (
    Tenant,
    TenantCounter,
    TenantIntegrationKey,
    TenantQuota,
    TenantQuotaCounter,
    TenantSettings,
)

__all__ = [
    "Tenant",
    "TenantQuota",
    "TenantSettings",
    "TenantCounter",
    "TenantIntegrationKey",
    "TenantQuotaCounter",
]
