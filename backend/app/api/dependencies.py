"""Dependency declarations shared across API routers."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import AsyncIterator
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.tenant import TENANT_HEADER, tenant_required
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

logger = logging.getLogger(__name__)


def _normalize_tenant_id(value: object) -> str | None:
    if value in (None, ""):
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return str(UUID(candidate))
    except (TypeError, ValueError):
        return None


def resolve_tenant_slug(request: Request) -> str | None:
    state_tenant = getattr(request.state, "tenant_slug", None)
    if state_tenant:
        return str(state_tenant).strip().lower()
    state_record = getattr(request.state, "tenant_record", None)
    if isinstance(state_record, Tenant):
        return str(state_record.slug).strip().lower()
    for header_name in (TENANT_HEADER, "x-tenant-slug"):
        value = request.headers.get(header_name)
        if value:
            return str(value).strip().lower()
    return None


def resolve_tenant_id(request: Request) -> str | None:
    state_tenant = getattr(request.state, "tenant_id", None)
    normalized = _normalize_tenant_id(state_tenant)
    if normalized:
        return normalized
    state_record = getattr(request.state, "tenant_record", None)
    if isinstance(state_record, Tenant):
        return _normalize_tenant_id(state_record.id)
    return None


def resolve_tenant_identifier(request: Request) -> str | None:
    return resolve_tenant_id(request) or resolve_tenant_slug(request)


def _resolve_tenant_slug(request: Request) -> str | None:
    return resolve_tenant_slug(request)


def _resolve_fallback_tenants(request: Request) -> list[str]:
    """Return fallback tenant slugs only for explicitly marked internal/test flows."""

    path = request.url.path
    allow_internal_fallback = bool(getattr(request.state, "allow_internal_tenant_fallback", False))
    if not allow_internal_fallback:
        logger.info(
            "tenant.resolve.fallback.disabled",
            extra={"path": path, "reason": "flag_not_set"},
        )
        return []

    settings = get_settings()
    if settings.app_env != "test":
        logger.warning(
            "tenant.resolve.fallback.blocked",
            extra={"path": path, "environment": settings.app_env},
        )
        return []

    allow_fallback = (
        path.startswith("/api/v1/auth")
        or path.startswith("/api/v1/portal")
        or path.startswith("/api/v1/webhooks/inbound/")
        or path.startswith("/api/v1/edo/webhooks/")
        or path.startswith("/api/v1/edo/webhook/status")
    )
    if not allow_fallback:
        return []

    default_slug = settings.default_tenant_slug
    candidates: list[str] = ["test", default_slug]
    deduped: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip().lower()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


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
    ensure_tenant_schema(tenant.slug, schema_name=tenant.schema_name, implicit=True)
    return tenant


async def get_auth_tenant_record(request: Request) -> Tenant:
    candidates: list[tuple[str, str]] = []
    tenant_id = resolve_tenant_id(request)
    tenant_slug = resolve_tenant_slug(request)
    if tenant_id:
        candidates.append((tenant_id, "request_state_or_header_id"))
    if tenant_slug and tenant_slug not in {value for value, _ in candidates}:
        candidates.append((tenant_slug, "request_state_or_header_slug"))

    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        from app.core.security import verify_token

        token = auth_header.split(None, 1)[1].strip()
        if token:
            try:
                claims = verify_token(token, expected_type="access")
            except HTTPException:
                claims = {}
            tenant_claim = str(claims.get("tenant") or "").strip().lower()
            if tenant_claim and tenant_claim not in {value for value, _ in candidates}:
                candidates.append((tenant_claim, "verified_access_token_claim"))

    if not candidates:
        candidates.extend((candidate, "internal_test_fallback") for candidate in _resolve_fallback_tenants(request))

    last_error: HTTPException | None = None
    for candidate, source in candidates:
        info = tenant_required(candidate)
        try:
            tenant = await _fetch_tenant_by_identifier(info.slug)
            logger.info(
                "tenant.resolve.success",
                extra={"path": request.url.path, "tenant": tenant.slug, "source": source},
            )
            return tenant
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
        logger.info(
            "tenant.resolve.success",
            extra={"path": request.url.path, "tenant": preloaded.slug, "source": "middleware_preloaded"},
        )
        return preloaded
    tenant_id = resolve_tenant_id(request)
    if tenant_id is not None:
        tenant = await _fetch_tenant_by_identifier(tenant_id)
        logger.info(
            "tenant.resolve.success",
            extra={"path": request.url.path, "tenant": tenant.slug, "source": "request_state_or_header_id"},
        )
        return tenant

    tenant_slug = resolve_tenant_slug(request)
    if tenant_slug is not None:
        info = tenant_required(tenant_slug)
        tenant = await _fetch_tenant_by_identifier(info.slug)
        logger.info(
            "tenant.resolve.success",
            extra={"path": request.url.path, "tenant": tenant.slug, "source": "request_state_or_header_slug"},
        )
        return tenant

    for candidate in _resolve_fallback_tenants(request):
        try:
            tenant = await _fetch_tenant_by_identifier(candidate)
            logger.info(
                "tenant.resolve.success",
                extra={"path": request.url.path, "tenant": tenant.slug, "source": "internal_test_fallback"},
            )
            return tenant
        except HTTPException as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                continue
            raise
    logger.warning("tenant.resolve.failed", extra={"path": request.url.path, "reason": "tenant_not_provided"})
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")


async def require_tenant_slug(request: Request) -> None:
    tenant_required(resolve_tenant_slug(request))


async def get_correlation_id(request: Request) -> str:
    """Extract correlation ID from request context (set by GlobalErrorHandlerMiddleware)."""
    return getattr(request.state, "correlation_id", "")


async def get_session(tenant: Tenant = Depends(get_tenant_record)) -> AsyncIterator[AsyncSession]:
    """Provide an async database session scoped to the current tenant."""

    async with get_tenant_session(
        tenant=tenant.slug,
        tenant_id=str(tenant.id),
        schema_name=tenant.schema_name,
    ) as session:
        info = getattr(session, "info", None)
        if info is None or not isinstance(info, dict):
            info = {}
            try:
                setattr(session, "info", info)
            except AttributeError:
                pass
        info["tenant"] = tenant.slug
        info["tenant_slug"] = tenant.slug
        info["tenant_schema"] = tenant.schema_name
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
