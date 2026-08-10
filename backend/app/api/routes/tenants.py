"""Tenant management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac, rbac, verify_token
from app.db.session import (
    AsyncSessionLocal,
    _create_tenant_schema,
    rearm_session_tenant_context,
    resolve_tenant_schema,
)
from app.models.models import RoleEnum, Tenant, TenantQuota, TenantSettings
from app.modules.subscription.registry import MODULE_REGISTRY
from app.repository import list_tenants
from app.schemas.tenant import (
    MyModuleEntry,
    MyModulesResponse,
    TenantCreate,
    TenantPage,
    TenantQuotaPatch,
    TenantQuotaRead,
    TenantRead,
)
from app.services.tenants.subscription import read_feature_grants

router = APIRouter(prefix="/tenants", tags=["tenants"])
admin_router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
_MANAGEMENT_ROLES = [RoleEnum.ADMIN.value, RoleEnum.CLIENT_ADMIN.value]


def _tenant_resource_id(
    tenant: Tenant = Depends(get_tenant_record),
) -> str | None:  # pragma: no cover - fastapi wiring
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
    # Authentication is mandatory: previously the admin check ran only ``if
    # credentials`` — an anonymous caller (tenant slug only, no token) skipped it and
    # received the tenant record page. ``_require_admin`` raises 401 when no token is
    # present and 403 for a non-admin role.
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
@audit_operation("create", "tenant")
async def create_tenant_endpoint(
    payload: TenantCreate,
    session: SessionDep,
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantRead:
    _require_admin(credentials)
    schema_name = resolve_tenant_schema(payload.slug)
    # Provisioning writes tenant_settings/tenant_quotas rows for the NEW tenant;
    # the caller's request session is pinned to the caller's tenant, so under
    # FORCE RLS (SEC-65) those inserts would be rejected. Use a trusted
    # shared-schema provisioning session like platform_tenants/bootstrap do.
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    ) as provisioning_session:
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
        provisioning_session.add(tenant)
        await provisioning_session.flush()
        tenant.s3_prefix = tenant.id
        provisioning_session.add(
            TenantSettings(
                tenant_id=tenant.id,
                schema_name=schema_name,
                s3_prefix=tenant.id,
            )
        )
        provisioning_session.add(
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
            await provisioning_session.commit()
        except IntegrityError as exc:
            await provisioning_session.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Tenant already exists") from exc

        await provisioning_session.refresh(tenant)
        result = TenantRead.model_validate(tenant)

    await _create_tenant_schema(schema_name)
    return result


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
    _: AccessContext = Depends(rbac()),
) -> dict[str, object]:
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    return {
        "tenant": TenantRead.model_validate(tenant),
        "quotas": TenantQuotaRead.model_validate(quota) if quota else None,
    }


@router.get("/me/modules", response_model=MyModulesResponse)
async def get_my_modules_endpoint(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = Depends(rbac()),
) -> MyModulesResponse:
    """Модули ЭТОГО арендатора: что включено и какие экраны кому принадлежат.

    Разд. 61.3 требует прятать навигацию и закрывать прямой переход по адресу
    для выключенного модуля. До этой ручки фронтенду было нечем: единственный
    источник признаков — `/billing/plan` — отдаёт фичи ТАРИФА БИЛЛИНГА, а
    фактическая выдача живёт в ``FeatureEnablement``. Два разных хранилища,
    которые расходятся: клиент, у которого модуль не выдан, всё равно видел
    пункт меню, если фича числилась в тарифе.

    Доступна любому пользователю арендатора, а не только владельцу: меню рисуют
    всем. Прежний источник был закрыт ролью owner/admin — у рядового
    пользователя список признаков всегда оставался пустым, и не скрывалось
    ничего.

    Отдаём ВСЕ модули, включая выключенные и ядро: «чего у нас нет» — такой же
    ответ, как «что есть», и по нему строится подсказка «модуль не подключён».
    """

    grants = await read_feature_grants(tenant)
    enabled_codes = grants.effective
    return MyModulesResponse(
        modules=[
            MyModuleEntry(
                code=module.code,
                title=module.title,
                category=module.category,
                is_core=module.is_core,
                # Ядро включено всегда; продаваемый модуль — только по выдаче.
                enabled=module.is_core or module.code in enabled_codes,
                trial_until=grants.trials.get(module.code),
                ui_routes=list(module.ui_routes),
            )
            for module in MODULE_REGISTRY
        ]
    )


@router.patch("/{tenant_id}/quotas", response_model=TenantQuotaRead)
@audit_operation("update_quota", "tenant")
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
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
    return await patch_tenant_quotas_endpoint(
        tenant_id, payload, session, tenant, credentials, access
    )


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
    if (
        tenant is None
        or tenant.slug != session.info.get("tenant")
        or tenant.id != current_tenant.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return TenantRead.model_validate(tenant)
