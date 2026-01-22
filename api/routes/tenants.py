"""Tenant management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import abac, verify_token
from app.models.models import RoleEnum, Tenant
from app.repository import list_tenants
from app.schemas.tenant import TenantPage, TenantRead

router = APIRouter(prefix="/tenants", tags=["tenants"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_MANAGEMENT_ROLES = [RoleEnum.ADMIN.value, RoleEnum.CLIENT_ADMIN.value]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:  # pragma: no cover - fastapi wiring
    return getattr(tenant, "id", None)


@router.get("", response_model=TenantPage)
async def list_tenants_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantPage:
    """List registered tenants with pagination."""

    if credentials:
        payload = verify_token(credentials.credentials, expected_type="access")
        role = str(payload.get("role") or "").lower()
        if role not in _MANAGEMENT_ROLES:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

        token_tenant_slug = str(payload.get("tenant") or "").strip() or None
        if token_tenant_slug and token_tenant_slug != tenant.slug:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant scope mismatch")

    items, total = await list_tenants(
        session, tenant.slug, limit=limit, offset=offset
    )
    return TenantPage(items=items, total=total)


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant_endpoint(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(abac(_tenant_resource_id, required_roles=_MANAGEMENT_ROLES, action="read")),
) -> TenantRead:
    """Return a tenant by identifier."""

    current_tenant = tenant
    tenant = await session.get(Tenant, tenant_id)
    _ = access  # silence linters
    if tenant is None or tenant.slug != session.info.get("tenant") or tenant.id != current_tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return TenantRead.model_validate(tenant)
