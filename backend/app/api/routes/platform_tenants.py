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
from app.db.session import AsyncSessionLocal, rearm_session_tenant_context
from app.models.models import RoleEnum, Tenant, TenantQuota
from app.modules.subscription import (
    FEATURE_CATALOG,
    PLANS,
    plan_code_for_features,
)
from app.modules.subscription.registry import MODULE_REGISTRY
from app.schemas.tenant import (
    FeatureCatalogEntry,
    ModuleRegistryEntry,
    ModuleRegistryResponse,
    ModuleTrialGrant,
    ModuleTrialResult,
    PlanCatalog,
    SubscriptionPlanRead,
    TenantFeatureRead,
    TenantFleetItem,
    TenantFleetPage,
    TenantPlanPatch,
    TenantProvisionRequest,
    TenantProvisionResult,
    TenantQuotaPatch,
    TenantQuotaRead,
    TenantRead,
    TenantStatusPatch,
)
from app.services.tenants.bootstrap import BootstrapTenantService
from app.services.tenants.subscription import (
    TrialError,
    apply_plan,
    grant_module_trial,
    read_feature_grants,
    revoke_module_trial,
)

router = APIRouter(prefix="/platform/tenants", tags=["platform-tenants"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
# The managing tenant's owner also administers the fleet: the frontend grants owner
# every permission (incl. manage-tenants), so the backend must not silently 403 them.
_MANAGEMENT_ROLES = frozenset(
    {RoleEnum.ADMIN.value, RoleEnum.CLIENT_ADMIN.value, RoleEnum.OWNER.value}
)


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


def _fleet_session() -> AsyncSession:
    """Shared-schema session for cross-tenant fleet reads/writes (quotas, plans).

    ``rls_bypass``: the fleet endpoints legitimately touch OTHER tenants'
    ``tenant_quotas`` (SEC-65-armed), which the managing tenant's request session
    cannot see under FORCE RLS. Authorisation is enforced by
    ``_require_managing_admin`` before any of this runs.
    """

    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


async def _load_quota(session: AsyncSession, tenant_id: str) -> TenantQuota | None:
    return (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def _build_fleet_item(session: AsyncSession, record: Tenant) -> TenantFleetItem:
    """Assemble one fleet row: quota, per-feature on/off, and the derived plan code."""

    quota = await _load_quota(session, record.id)
    grants = await read_feature_grants(record)
    effective = grants.effective
    features = [
        TenantFeatureRead(
            code=code,
            title=title,
            on=code in effective,
            trial_until=grants.trials.get(code),
        )
        for code, title in FEATURE_CATALOG.items()
    ]
    return TenantFleetItem(
        tenant=TenantRead.model_validate(record),
        quotas=TenantQuotaRead.model_validate(quota) if quota else None,
        # Тариф выводится ТОЛЬКО из бессрочной части (BIZ-61 срез-3): подмешай
        # сюда пробный доступ — и клиент с «Базовым» плюс демонстрация СОУТ
        # перестанет совпадать с любым тарифом и превратится в «свой набор».
        plan=plan_code_for_features(grants.permanent),
        features=features,
    )


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

    async with _fleet_session() as fleet_session:
        items = [await _build_fleet_item(fleet_session, record) for record in rows]
    return TenantFleetPage(
        items=items,
        total=int(total or 0),
        managing_tenant_slug=get_settings().managing_tenant_slug,
    )


@router.get("/plans", response_model=PlanCatalog)
async def list_plans_endpoint(
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> PlanCatalog:
    """The subscription tier catalogue the fleet UI renders its plan picker from."""

    _require_managing_admin(credentials, tenant)
    return PlanCatalog(
        plans=[
            SubscriptionPlanRead(
                code=plan.code,
                title=plan.title,
                feature_codes=sorted(plan.features),
                quotas=plan.quotas,
            )
            for plan in PLANS.values()
        ],
        features=[
            FeatureCatalogEntry(code=code, title=title) for code, title in FEATURE_CATALOG.items()
        ],
    )


@router.get("/modules", response_model=ModuleRegistryResponse)
async def list_module_registry(
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> ModuleRegistryResponse:
    """Реестр модулей платформы (разд. 61.1) — источник истины о том, что вообще
    можно включать и выключать.

    Отдаёт ВСЕ модули, включая ядро: на вопрос «что нельзя выключить» должен
    отвечать реестр, а не память разработчика. Ядро помечено ``is_core`` и в
    тарифы не входит.

    ``ui_routes`` нужны фронтенду, чтобы прятать навигацию выключенного модуля
    (разд. 61.3). Держать эту связь на стороне фронта значило бы описать её
    второй раз — и однажды разойтись с бэкендом.
    """

    _require_managing_admin(credentials, tenant)
    return ModuleRegistryResponse(
        modules=[
            ModuleRegistryEntry(
                code=module.code,
                title=module.title,
                category=module.category,
                is_core=module.is_core,
                depends_on=list(module.depends_on),
                ui_routes=list(module.ui_routes),
                permissions=list(module.permissions),
            )
            for module in MODULE_REGISTRY
        ]
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
    # rls_bypass: provisioning legitimately inserts rows (e.g. the tenant's ``company``)
    # for another tenant on a tenant-less shared session, so the SEC-65 RLS predicate
    # (tenant_id == app.current_tenant) would otherwise reject the INSERT under FORCE RLS.
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
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
        # commit() drops the transaction-local GUCs — the bypass flag included.
        # Harmless today (Tenant is shared), but re-arm so the pattern is safe
        # once any table this session touches gets RLS (SEC-65).
        await rearm_session_tenant_context(provisioning_session)
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
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
    async with _fleet_session() as fleet_session:
        quota = await _load_quota(fleet_session, tenant_id)
        if quota is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant quota not found")

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(quota, key, value)
        await fleet_session.commit()
        result = TenantQuotaRead.model_validate(quota)
    return result


@router.patch("/{tenant_id}/plan", response_model=TenantFleetItem)
@audit_operation("update_plan", "tenant")
async def patch_tenant_plan_endpoint(
    tenant_id: str,
    payload: TenantPlanPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantFleetItem:
    """Move a tenant onto a subscription tier: unlock its features and set its quotas."""

    _require_managing_admin(credentials, tenant)
    plan = PLANS.get(payload.plan.strip().lower())
    if plan is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown plan '{payload.plan}'",
        )
    target = await session.get(Tenant, tenant_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    async with _fleet_session() as fleet_session:
        await apply_plan(fleet_session, target, plan)
        await fleet_session.commit()
        item = await _build_fleet_item(fleet_session, target)
    return item


@router.post("/{tenant_id}/modules/{code}/trial", response_model=ModuleTrialResult)
@audit_operation("grant_module_trial", "tenant")
async def grant_module_trial_endpoint(
    tenant_id: str,
    code: str,
    payload: ModuleTrialGrant,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> ModuleTrialResult:
    """Выдать клиенту модуль на срок (разд. 61.2, «временный доступ на N дней»).

    Третий источник включения наравне с тарифом и надбавкой. До него «дать
    посмотреть на две недели» означало включить модуль и понадеяться на память
    менеджера — модуль оставался открытым бесплатно.
    """

    _require_managing_admin(credentials, tenant)
    target = await session.get(Tenant, tenant_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    try:
        expires_at = await grant_module_trial(target, code, payload.days)
    except TrialError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    return ModuleTrialResult(code=code, title=FEATURE_CATALOG[code], trial_until=expires_at)


@router.delete("/{tenant_id}/modules/{code}/trial", response_model=ModuleTrialResult)
@audit_operation("revoke_module_trial", "tenant")
async def revoke_module_trial_endpoint(
    tenant_id: str,
    code: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> ModuleTrialResult:
    """Прекратить пробный доступ досрочно.

    Бессрочную выдачу не трогает: модуль из тарифа снимается сменой тарифа,
    иначе эта кнопка однажды заберёт оплаченное.
    """

    _require_managing_admin(credentials, tenant)
    target = await session.get(Tenant, tenant_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    if code not in FEATURE_CATALOG:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown module '{code}'")
    if not await revoke_module_trial(target, code):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"У арендатора нет пробного доступа к модулю '{code}'",
        )
    return ModuleTrialResult(code=code, title=FEATURE_CATALOG[code], trial_until=None)
