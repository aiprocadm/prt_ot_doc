"""Dependency declarations shared across API routers."""
from __future__ import annotations

from functools import lru_cache
from typing import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TENANT_HEADER, get_current_tenant, tenant_required
from app.db.session import AsyncSessionLocal, ensure_tenant_schema
from app.models.models import Tenant
from app.services.file_storage import FileStorageService
from app.services.integrations import (
    BaseAccountingIntegration,
    BaseEDOIntegration,
    BaseEISOTIntegration,
    BaseFRDOIntegration,
    get_accounting_integration,
    get_edo_integration,
    get_eisot_integration,
    get_frdo_integration,
)


def _resolve_tenant_slug(request: Request) -> str | None:
    for header_name in (TENANT_HEADER, "x-tenant-slug"):
        value = request.headers.get(header_name)
        if value:
            return value
    return None


async def get_tenant_record(request: Request) -> Tenant:
    tenant_slug = _resolve_tenant_slug(request)
    info = tenant_required(tenant_slug) if tenant_slug is not None else get_current_tenant()
    async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
        result = await session.execute(select(Tenant).where(Tenant.slug == info.slug))
        tenant = result.scalar_one_or_none()
        if tenant is None or not tenant.is_active:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    ensure_tenant_schema(info.slug)
    return tenant


async def require_tenant_slug(request: Request) -> None:
    tenant_required(_resolve_tenant_slug(request))


async def get_session(tenant: Tenant = Depends(get_tenant_record)) -> AsyncIterator[AsyncSession]:
    """Provide an async database session scoped to the current tenant."""

    async with AsyncSessionLocal(tenant=tenant.slug) as session:
        info = getattr(session, "info", None)
        if info is None or not isinstance(info, dict):
            info = {}
            try:
                setattr(session, "info", info)
            except AttributeError:
                pass
        info["tenant"] = tenant.slug
        if getattr(tenant, "id", None) is not None:
            info["tenant_id"] = str(tenant.id)
        info.setdefault("token_tenant_id", None)
        yield session


@lru_cache()
def get_file_storage_service() -> FileStorageService:
    """Return a cached storage service instance."""

    service = FileStorageService.default()
    service.ensure_ready()
    return service


def get_accounting_integration_service() -> BaseAccountingIntegration:
    """Provide the configured 1C integration implementation."""

    return get_accounting_integration()


def get_edo_integration_service() -> BaseEDOIntegration:
    """Provide the configured EDO/ЭП integration implementation."""

    return get_edo_integration()


def get_frdo_integration_service() -> BaseFRDOIntegration:
    """Provide the configured FRDO integration implementation."""

    return get_frdo_integration()


def get_eisot_integration_service() -> BaseEISOTIntegration:
    """Provide the configured EISOT integration implementation."""

    return get_eisot_integration()
