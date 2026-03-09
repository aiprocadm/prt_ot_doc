"""Dependency declarations shared across API routers."""
from __future__ import annotations

from functools import lru_cache
from typing import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenant import TENANT_HEADER, get_current_tenant, tenant_required
from app.db.session import AsyncSessionLocal, ensure_tenant_schema, get_tenant_session
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
    state_tenant = getattr(request.state, "tenant_id", None)
    if state_tenant:
        return str(state_tenant)
    for header_name in (TENANT_HEADER, "x-tenant-slug"):
        value = request.headers.get(header_name)
        if value:
            return value
    if request.url.path.startswith("/api/v1/auth"):
        return get_settings().default_tenant_slug
    return None


async def _fetch_tenant_by_identifier(identifier: str) -> Tenant:
    async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
        filters = [Tenant.slug == identifier, Tenant.code == identifier]
        if len(identifier) == 36:
            filters.append(Tenant.id == identifier)
        result = await session.execute(select(Tenant).where(or_(*filters)))
        tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    if not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant inactive")
    ensure_tenant_schema(tenant.slug)
    return tenant


async def get_auth_tenant_record(request: Request) -> Tenant:
    tenant_slug = _resolve_tenant_slug(request)
    candidates: list[str] = []
    if tenant_slug:
        candidates.append(tenant_slug)
    else:
        candidates.extend([get_settings().default_tenant_slug, "test"])

    last_error: HTTPException | None = None
    for candidate in candidates:
        info = tenant_required(candidate)
        try:
            return await _fetch_tenant_by_identifier(info.slug)
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                last_error = exc
                continue
            raise

    if last_error is not None:
        raise last_error
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")


async def get_tenant_record(request: Request) -> Tenant:
    preloaded = getattr(request.state, "tenant_record", None)
    if isinstance(preloaded, Tenant):
        return preloaded
    tenant_slug = _resolve_tenant_slug(request)
    info = tenant_required(tenant_slug)
    return await _fetch_tenant_by_identifier(info.slug)


async def require_tenant_slug(request: Request) -> None:
    tenant_required(_resolve_tenant_slug(request))


async def get_session(tenant: Tenant = Depends(get_tenant_record)) -> AsyncIterator[AsyncSession]:
    """Provide an async database session scoped to the current tenant."""

    async with get_tenant_session(tenant=tenant.slug, schema_name=tenant.schema_name) as session:
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
