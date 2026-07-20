"""Tenant fleet management for the managing ("platform") tenant.

``app.api.routes.tenants`` stays tenant-scoped: every caller only ever sees its own
record. Subscription management needs the opposite — one designated tenant that
provisions, suspends and re-quotas everybody else. That privilege is granted here and
nowhere else: :func:`_require_managing_admin` demands both an admin role *and* that the
request runs under ``settings.managing_tenant_slug``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.security import verify_token
from app.db.session import AsyncSessionLocal
from app.models.models import RoleEnum, Tenant, TenantQuota
from app.schemas.tenant import (
    TenantFleetItem,
    TenantFleetPage,
    TenantProvisionRequest,
    TenantProvisionResult,
    TenantQuotaPatch,
    TenantQuotaRead,
    TenantRead,
    TenantStatusPatch,
)
from app.services.tenants.bootstrap import BootstrapTenantService

router = APIRouter(prefix="/platform/tenants", tags=["platform-tenants"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_MANAGEMENT_ROLES = frozenset({RoleEnum.ADMIN.value, RoleEnum.CLIENT_ADMIN.value})


def _require_managing_admin(
    credentials: HTTPAuthorizationCredentials | None,
    tenant: Tenant,
) -> dict[str, object]:
    """Authorise a fleet operation, or raise 401/403.

    Three independent checks: a valid access token, an admin role, and the request being
    scoped to the managing tenant. The last one is what keeps a regular tenant's admin
    from reaching other tenants' records.
    """

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = verify_token(credentials.credentials, expected_type="access")
    if str(payload.get("role") or "").lower() not in _MANAGEMENT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    managing_slug = get_settings().managing_tenant_slug
    if tenant.slug.strip().lower() != managing_slug:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant fleet management is not available")
    # A token minted for another tenant must not act through the managing tenant's slug.
    token_slug = str(payload.get("tenant") or "").strip().lower()
    if token_slug and token_slug != managing_slug:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant scope mismatch")
    return payload


async def _load_quota(session: AsyncSession, tenant_id: str) -> TenantQuota | None:
    return (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
    ).scalar_one_or_none()


@router.get("", response_model=TenantFleetPage)
async def list_tenant_fleet_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TenantFleetPage:
    _require_managing_admin(credentials, tenant)

    total = await session.scalar(select(func.count()).select_from(Tenant.__table__))
    rows = (
        await session.execute(
            select(Tenant).order_by(Tenant.created_at.asc()).offset(offset).limit(limit)
        )
    ).scalars()

    items = []
    for record in rows:
        quota = await _load_quota(session, record.id)
        items.append(
            TenantFleetItem(
                tenant=TenantRead.model_validate(record),
                quotas=TenantQuotaRead.model_validate(quota) if quota else None,
            )
        )
    return TenantFleetPage(
        items=items,
        total=int(total or 0),
        managing_tenant_slug=get_settings().managing_tenant_slug,
    )


@router.post("", response_model=TenantProvisionResult, status_code=status.HTTP_201_CREATED)
@audit_operation("provision", "tenant")
async def provision_tenant_endpoint(
    payload: TenantProvisionRequest,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantProvisionResult:
    """Create a ready-to-use tenant: record, schema, quotas, owner login and starter pack.

    ``session`` is the managing tenant's request session. Provisioning itself does not use
    it — it writes through ``provisioning_session`` below — but ``@audit_operation`` needs
    it to record the event inside this request's own transaction.
    """

    _require_managing_admin(credentials, tenant)
    slug = payload.slug.strip().lower()
    if slug == get_settings().managing_tenant_slug:
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists")

    # The request session is bound to the managing tenant's schema; bootstrapping writes
    # rows for a *different* tenant, so it runs on a shared-schema session exactly like
    # ``scripts/bootstrap_tenant.py`` does.
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as provisioning_session:
        existing = (
            await provisioning_session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists")

        service = BootstrapTenantService(provisioning_session)
        try:
            summary = await service.run(
                tenant_slug=slug,
                tenant_name=payload.name.strip(),
                owner_email=str(payload.owner_email),
                owner_password=payload.owner_password,
                demo=payload.demo_data,
            )
            created = (
                await provisioning_session.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one()
            if payload.kind != created.kind:
                created.kind = payload.kind
            await provisioning_session.commit()
        except IntegrityError as exc:
            await provisioning_session.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists") from exc
        await provisioning_session.refresh(created)
        result = TenantRead.model_validate(created)

    return TenantProvisionResult(
        tenant=result,
        created=summary.created,
        reused=summary.reused,
        warnings=summary.warnings,
    )


@router.patch("/{tenant_id}/status", response_model=TenantRead)
@audit_operation("update_status", "tenant")
async def patch_tenant_status_endpoint(
    tenant_id: str,
    payload: TenantStatusPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantRead:
    """Enable or suspend a tenant — the subscription on/off switch."""

    _require_managing_admin(credentials, tenant)
    target = await session.get(Tenant, tenant_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    # Suspending the managing tenant would lock everyone out of fleet management.
    if target.slug.strip().lower() == get_settings().managing_tenant_slug:
        raise HTTPException(status.HTTP_409_CONFLICT, "Managing tenant cannot be suspended")

    target.is_active = payload.is_active
    await session.commit()
    await session.refresh(target)
    return TenantRead.model_validate(target)


@router.patch("/{tenant_id}/quotas", response_model=TenantQuotaRead)
@audit_operation("update_quota", "tenant")
async def patch_fleet_quotas_endpoint(
    tenant_id: str,
    payload: TenantQuotaPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantQuotaRead:
    """Adjust another tenant's limits — the subscription plan."""

    _require_managing_admin(credentials, tenant)
    if await session.get(Tenant, tenant_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    quota = await _load_quota(session, tenant_id)
    if quota is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant quota not found")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(quota, key, value)
    await session.commit()
    await session.refresh(quota)
    return TenantQuotaRead.model_validate(quota)
