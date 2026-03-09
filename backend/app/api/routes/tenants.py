"""Tenant management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import abac, verify_token
from app.db.session import _create_tenant_schema, resolve_tenant_schema
from app.models.models import RoleEnum, Tenant, TenantQuota, TenantSettings
from app.repository import list_tenants
from app.schemas.tenant import (
    TenantCreate,
    TenantPage,
    TenantQuotaPatch,
    TenantQuotaRead,
    TenantRead,
)

router = APIRouter(prefix="/tenants", tags=["tenants"])
admin_router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_MANAGEMENT_ROLES = [RoleEnum.ADMIN.value, RoleEnum.CLIENT_ADMIN.value]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:  # pragma: no cover - fastapi wiring
    return getattr(tenant, "id", None)


def _require_admin(credentials: HTTPAuthorizationCredentials | None) -> dict[str, object]:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = verify_token(credentials.credentials, expected_type="access")
    role = str(payload.get("role") or "").lower()
    if role not in _MANAGEMENT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    return payload


@router.get("", response_model=TenantPage)
async def list_tenants_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantPage:
    if credentials:
        payload = _require_admin(credentials)
        token_tenant_slug = str(payload.get("tenant") or "").strip() or None
        if token_tenant_slug and token_tenant_slug != tenant.slug:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant scope mismatch")

    items, total = await list_tenants(session, tenant.slug, limit=limit, offset=offset)
    return TenantPage(items=items, total=total)


@admin_router.get("", response_model=TenantPage)
async def list_tenants_admin_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantPage:
    return await list_tenants_endpoint(session, tenant, credentials, limit, offset)


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant_endpoint(
    payload: TenantCreate,
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantRead:
    _require_admin(credentials)
    schema_name = resolve_tenant_schema(payload.slug)
    tenant = Tenant(
        slug=payload.slug,
        code=(payload.code or payload.slug),
        name=payload.name,
        contact_email=payload.contact_email,
        parent_id=payload.parent_id,
        kind=payload.kind,
        schema_name=schema_name,
        s3_prefix="",
        is_active=True,
    )
    session.add(tenant)
    await session.flush()
    tenant.s3_prefix = tenant.id
    session.add(
        TenantSettings(
            tenant_id=tenant.id,
            schema_name=schema_name,
            s3_prefix=tenant.id,
        )
    )
    session.add(
        TenantQuota(
            tenant_id=tenant.id,
            max_parallel_jobs=4,
            max_doc_generations_per_month=5000,
            max_storage_mb=10240,
            monthly_edo_outgoing=0,
            enforce_billing_gate=False,
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists") from exc

    await _create_tenant_schema(schema_name)
    await session.refresh(tenant)
    return TenantRead.model_validate(tenant)


@admin_router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant_admin_endpoint(
    payload: TenantCreate,
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantRead:
    return await create_tenant_endpoint(payload, session, credentials)


@router.get("/me")
async def get_my_tenant_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
) -> dict[str, object]:
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    return {
        "tenant": TenantRead.model_validate(tenant),
        "quotas": TenantQuotaRead.model_validate(quota) if quota else None,
    }


@router.patch("/{tenant_id}/quotas", response_model=TenantQuotaRead)
async def patch_tenant_quotas_endpoint(
    tenant_id: str,
    payload: TenantQuotaPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(abac(_tenant_resource_id, required_roles=_MANAGEMENT_ROLES, action="write")),
) -> TenantQuotaRead:
    _ = access
    _require_admin(credentials)
    if tenant_id != tenant.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant scope mismatch")
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if quota is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant quota not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(quota, key, value)
    await session.commit()
    await session.refresh(quota)
    return TenantQuotaRead.model_validate(quota)


@admin_router.patch("/{tenant_id}/quotas", response_model=TenantQuotaRead)
async def patch_tenant_quotas_admin_endpoint(
    tenant_id: str,
    payload: TenantQuotaPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    access=Depends(abac(_tenant_resource_id, required_roles=_MANAGEMENT_ROLES, action="write")),
) -> TenantQuotaRead:
    return await patch_tenant_quotas_endpoint(tenant_id, payload, session, tenant, credentials, access)


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant_endpoint(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(abac(_tenant_resource_id, required_roles=_MANAGEMENT_ROLES, action="read")),
) -> TenantRead:
    current_tenant = tenant
    tenant = await session.get(Tenant, tenant_id)
    _ = access
    if tenant is None or tenant.slug != session.info.get("tenant") or tenant.id != current_tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return TenantRead.model_validate(tenant)
