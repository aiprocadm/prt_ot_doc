"""Кабинет арендаторов: владелец платформы и партнёры-реселлеры.

``app.api.routes.tenants`` остаётся про «свою» запись: каждый видит только себя.
Управление подпиской — противоположная задача: кто-то заводит, приостанавливает
и переквотирует ДРУГИХ. Это право выдаётся здесь и больше нигде.

До BIZ-52 среза-2 право было ровно одно и неделимое: «ты управляющий арендатор»
(`settings.managing_tenant_slug`). Разд. 52.4 требует второй кабинет — партнёра,
который ведёт СВОИХ клиентов; а разд. 52.1 требует, чтобы партнёр при этом не
видел ни чужих клиентов, ни данных владельца платформы. Поэтому проверка
разделена надвое: :func:`_require_fleet_actor` отвечает «кто пришёл», а
:class:`FleetScope` — «что ему принадлежит». Все выборки и правки сужаются
областью; чужой арендатор отвечает 404, а не 403, чтобы не подтверждать даже
факт его существования.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.hierarchy_errors import hierarchy_http_error
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.security import verify_token
from app.db.session import AsyncSessionLocal, rearm_session_tenant_context
from app.domains.reseller import (
    FleetScope,
    HierarchyViolation,
    TenantNode,
    is_in_scope,
    plan_tenant_creation,
    resolve_fleet_scope,
)
from app.domains.reseller.cascade import CascadeImpact, plan_suspension_cascade
from app.domains.reseller.config_transfer import build_config, check_config
from app.domains.reseller.fleet_metrics import NOT_MEASURED_METRICS
from app.domains.reseller.industries import (
    INDUSTRIES,
    UnknownIndustryError,
    resolve_industry,
)
from app.domains.reseller.own_limits import build_limit_lines
from app.domains.reseller.pack_updates import PackUpdate, plan_pack_update
from app.domains.reseller.subbilling import check_plan_ceiling, is_ceiling_applicable
from app.models.master_data import Position
from app.models.models import RoleEnum, Tenant, TenantQuota
from app.models.safety_core import Hazard, RiskMeasure
from app.models.tenant_billing import BillingUsageCounter, TenantCounter
from app.modules.subscription import (
    FEATURE_CATALOG,
    PLANS,
    plan_code_for_features,
)
from app.modules.subscription.registry import MODULE_REGISTRY
from app.schemas.tenant import (
    FeatureCatalogEntry,
    FleetUsageReport,
    IndustryList,
    IndustryRead,
    ModuleRegistryEntry,
    ModuleRegistryResponse,
    ModuleTrialGrant,
    ModuleTrialResult,
    OwnLimitLine,
    OwnLimitsReport,
    PackUpdatePreview,
    PackUpdateResult,
    PlanCatalog,
    SubscriptionPlanRead,
    TenantCascadePreview,
    TenantConfigApplyRequest,
    TenantConfigApplyResult,
    TenantConfigExport,
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
    TenantStatusResult,
    TenantUsageRow,
)
from app.services.audit import AuditService
from app.services.tenants.bootstrap import BootstrapTenantService
from app.services.tenants.bootstrap.service import STARTER_PACK_ROOT
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


def _fleet_node(record: Tenant) -> TenantNode:
    """Свести ORM-строку к полям, которые нужны правилам иерархии и области."""

    return TenantNode(
        id=record.id,
        slug=record.slug,
        kind=record.kind,
        parent_id=record.parent_id,
        is_active=bool(record.is_active),
    )


def _require_fleet_actor(
    credentials: HTTPAuthorizationCredentials | None,
    tenant: Tenant,
) -> tuple[dict[str, object], FleetScope]:
    """Авторизовать операцию с флотом и вернуть область пришедшего.

    Четыре независимые проверки: действующий токен, управляющая роль, совпадение
    арендатора токена с арендатором запроса и — новое в срезе-2 — уровень
    арендатора. Раньше третья проверка была «ты управляющий», и она же выполняла
    роль четвёртой; теперь уровень решает, ЧТО именно доступно, а не только
    «пускать или нет».
    """

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    payload = verify_token(credentials.credentials, expected_type="access")
    if str(payload.get("role") or "").lower() not in _MANAGEMENT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    # Токен, выписанный другому арендатору, не должен действовать через чужой
    # слаг. Сравниваем с арендатором ЗАПРОСА (а не с управляющим, как раньше):
    # партнёр приходит под своим слагом, и жёсткая привязка к управляющему
    # закрыла бы ему кабинет.
    token_slug = str(payload.get("tenant") or "").strip().lower()
    if token_slug and token_slug != tenant.slug.strip().lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tenant scope mismatch")

    try:
        scope = resolve_fleet_scope(
            _fleet_node(tenant), managing_slug=get_settings().managing_tenant_slug
        )
    except HierarchyViolation as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code=exc.code, message=exc.message, error_type="platform-tenants"
            ),
        ) from exc
    return payload, scope


def _require_managing_admin(
    credentials: HTTPAuthorizationCredentials | None,
    tenant: Tenant,
) -> dict[str, object]:
    """Операция ТОЛЬКО для владельца платформы, партнёру закрыта.

    Осталась для поверхностей, которые смотрят на платформу целиком, а не на
    свой контур: например, журнал использования устаревших API
    (`routes/deprecation_admin.py`) — там видно потребление ВСЕХ арендаторов.
    Открывать такое партнёру нельзя, поэтому уровень проверяется явно.
    """

    payload, scope = _require_fleet_actor(credentials, tenant)
    if not scope.sees_everything:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="PLATFORM_OWNER_ONLY",
                message="Раздел доступен только владельцу платформы",
                error_type="platform-tenants",
            ),
        )
    return payload


def _scope_filter(scope: FleetScope):
    """Условие выборки по области. Для платформы — без сужения.

    Условие строится ЗДЕСЬ, а не в каждой ручке: разъехавшись, «свой клиент»
    начал бы означать разное в списке и в правке.
    """

    if scope.sees_everything:
        return None
    return Tenant.parent_id == scope.owner_id


async def _load_in_scope(session: AsyncSession, tenant_id: str, scope: FleetScope) -> Tenant:
    """Взять арендатора, если он принадлежит области, иначе 404.

    Именно 404, а не 403: 403 подтвердил бы, что арендатор с таким id
    существует, — партнёр не должен узнавать даже это о чужом контуре
    (то же правило, что в BIZ-49 срез-9).
    """

    target = await session.get(Tenant, tenant_id)
    if target is None or not is_in_scope(scope, _fleet_node(target)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return target


async def _enforce_plan_ceiling(scope: FleetScope, actor: Tenant, plan: Any) -> None:
    """Партнёр не выдаёт клиенту модули, которых нет у него самого (разд. 52.4).

    Набор партнёра берётся ДЕЙСТВУЮЩИЙ, вместе с пробными выдачами: пока модуль
    у него работает, он вправе показать его клиенту. Кончится проба — следующая
    смена тарифа уже не пройдёт; это честнее, чем запрещать заранее.
    """

    if not is_ceiling_applicable(actor_sees_everything=scope.sees_everything):
        return
    own = await read_feature_grants(actor)
    verdict = check_plan_ceiling(
        plan_features=set(plan.features), reseller_features=own.effective
    )
    if verdict.allowed:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code="RESELLER_PLAN_EXCEEDS_OWN",
            message=verdict.reason,
            error_type="platform-tenants",
        ),
    )


def _require_commercial_rights(scope: FleetScope) -> None:
    """Тариф, квоты и пробный доступ пока меняет только владелец платформы."""

    if scope.may_change_commercials:
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        detail=api_problem_detail(
            code="FLEET_COMMERCIALS_PLATFORM_ONLY",
            message=(
                "Тарифы, квоты и пробный доступ выдаёт владелец платформы: "
                "у партнёра ещё нет собственного потолка (суб-биллинг, разд. 52.4)"
            ),
            error_type="platform-tenants",
        ),
    )


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
    _payload, scope = _require_fleet_actor(credentials, tenant)

    # Область сужает И выборку, И подсчёт итога. Посчитай итог по всей таблице —
    # и партнёр увидит «клиентов: 214» над списком из трёх своих: постраничная
    # навигация уводила бы его на пустые страницы, а число выдавало бы размер
    # чужого флота.
    condition = _scope_filter(scope)
    count_stmt = select(func.count()).select_from(Tenant.__table__)
    rows_stmt = select(Tenant).order_by(Tenant.created_at.asc())
    if condition is not None:
        count_stmt = count_stmt.where(condition)
        rows_stmt = rows_stmt.where(condition)

    total = await session.scalar(count_stmt)
    rows = (await session.execute(rows_stmt.offset(offset).limit(limit))).scalars()

    async with _fleet_session() as fleet_session:
        items = [await _build_fleet_item(fleet_session, record) for record in rows]
    return TenantFleetPage(
        items=items,
        total=int(total or 0),
        managing_tenant_slug=get_settings().managing_tenant_slug,
        viewer_level="platform" if scope.sees_everything else "reseller",
        can_manage_commercials=scope.may_change_commercials,
    )


@router.get("/me/limits", response_model=OwnLimitsReport)
async def read_own_limits(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    period: str | None = Query(None, pattern=r"^\d{6}$"),
) -> OwnLimitsReport:
    """Свои лимиты и свой расход (разд. 52.4).

    Партнёр не входит в собственную область (решение среза-2: иначе он мог бы
    приостановить сам себя), поэтому его строки нет ни в списке клиентов, ни в
    отчёте о расходе — свои квоты он не видел вовсе. Ручка `GET /tenants/me`
    лимиты отдаёт, но НЕ показывает расход и фронтом не вызывается нигде.

    Здесь — пара «сколько можно и сколько занято»: лимит без расхода не
    отвечает на вопрос «хватит ли до конца месяца».

    Объявлена ДО `/{tenant_id}`: иначе `me` попало бы в него как идентификатор.
    """

    _payload, _scope = _require_fleet_actor(credentials, tenant)
    yyyymm = period or datetime.now(tz=timezone.utc).strftime("%Y%m")

    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    generations = (
        await session.execute(
            select(TenantCounter.doc_generations).where(
                TenantCounter.tenant_id == tenant.id, TenantCounter.yyyymm == yyyymm
            )
        )
    ).scalar_one_or_none()
    storage = (
        await session.execute(
            select(BillingUsageCounter.s3_bytes_used).where(
                BillingUsageCounter.tenant_id == tenant.id,
                BillingUsageCounter.period_yyyymm == int(yyyymm),
            )
        )
    ).scalar_one_or_none()

    lines = build_limit_lines(
        max_doc_generations_per_month=quota.max_doc_generations_per_month if quota else None,
        max_storage_mb=quota.max_storage_mb if quota else None,
        monthly_edo_outgoing=quota.monthly_edo_outgoing if quota else None,
        max_parallel_jobs=quota.max_parallel_jobs if quota else None,
        doc_generations_used=int(generations or 0),
        storage_bytes_used=int(storage or 0),
    )
    return OwnLimitsReport(
        period=yyyymm,
        tenant_slug=tenant.slug,
        items=[
            OwnLimitLine(
                code=line.code,
                title=line.title,
                unit=line.unit,
                limit=line.limit,
                used=line.used,
                remaining=line.remaining,
                exhausted=line.exhausted,
            )
            for line in lines
        ],
    )


@router.get("/industries", response_model=IndustryList)
async def read_industries(
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> IndustryList:
    """Отрасли, доступные при заведении клиента (разд. 52.3).

    Список отдаёт СЕРВЕР, а не зашивает интерфейс: набор файлов эталонов живёт
    на сервере, и вторая копия списка на фронте разошлась бы с ним при первой же
    новой отрасли — человек выбрал бы отрасль, для которой набора нет.

    Объявлена ДО `/{tenant_id}`: иначе слово `industries` попало бы в него как
    идентификатор.
    """

    _require_fleet_actor(credentials, tenant)
    return IndustryList(
        items=[
            IndustryRead(code=item.code, title=item.title) for item in INDUSTRIES
        ]
    )


@router.get("/usage", response_model=FleetUsageReport)
async def read_fleet_usage(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    period: str | None = Query(None, pattern=r"^\d{6}$"),
) -> FleetUsageReport:
    """Потребление по области: чем и сколько пользуются клиенты (разд. 52.4).

    Partner видит расход СВОИХ клиентов, владелец платформы — всего флота: та же
    область, что и у списка. Считать по всей таблице значило бы показать
    партнёру чужой оборот.

    **Срез-13 добавил метрики, которые СОБИРАЮТСЯ.** Раньше кабинет показывал
    только генерации документов, хотя партнёр выставляет клиенту счёт за услугу
    целиком. Добавлены занятое хранилище и активные сотрудники — их пишут
    `modules/files/api.py` и задача `billing.recompute_active_workers`.

    **Чего в отчёте НЕТ и почему** (поле `not_measured` говорит это вслух):

    * ЭДО — счётчик `usage_counters.edo_outgoing` существует и даже имеет метод
      инкремента, но его НЕ ВЫЗЫВАЕТ НИКТО: провайдер отправки ЭДО не реализован
      (известный остаток BIZ-50). Показать ноль значило бы сказать «клиент не
      пользуется ЭДО» вместо правды «мы это не считаем».
    * Вызовы API — колонка есть, писателя нет вовсе.

    Генерации по-прежнему берутся из `tenant_counters`: это работающий источник,
    проверенный срезом-8, и менять числа на глазах у партнёра ради единообразия
    таблиц нельзя. **Долг, который стоит назвать:** генерации пишутся в ДВЕ
    таблицы разными путями (`tenancy_quotas` → `tenant_counters`,
    `documents/generate` → `usage_counters`), и однажды они разойдутся.

    Период — месяц `ГГГГММ`; без него берётся текущий.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    yyyymm = period or datetime.now(tz=timezone.utc).strftime("%Y%m")

    condition = _scope_filter(scope)
    # LEFT JOIN к обеим таблицам: клиент без единой генерации, но с полусотней
    # сотрудников и гигабайтом файлов расходует услугу, и в отчёте он обязан
    # быть. Прежнее правило «нулевой расход не показываем» было верным, пока
    # метрика была ОДНА, и перестало быть верным, когда их стало три.
    stmt = (
        select(
            Tenant.id,
            Tenant.slug,
            Tenant.name,
            TenantCounter.doc_generations,
            BillingUsageCounter.s3_bytes_used,
            BillingUsageCounter.active_workers,
        )
        .join(
            TenantCounter,
            (TenantCounter.tenant_id == Tenant.id) & (TenantCounter.yyyymm == yyyymm),
            isouter=True,
        )
        .join(
            BillingUsageCounter,
            (BillingUsageCounter.tenant_id == Tenant.id)
            & (BillingUsageCounter.period_yyyymm == int(yyyymm)),
            isouter=True,
        )
    )
    if condition is not None:
        stmt = stmt.where(condition)

    rows = [
        TenantUsageRow(
            tenant_id=row[0],
            slug=row[1],
            name=row[2],
            doc_generations=int(row[3] or 0),
            storage_bytes=int(row[4] or 0),
            active_workers=int(row[5] or 0),
        )
        for row in (await session.execute(stmt.order_by(Tenant.created_at.asc()))).all()
    ]
    # Клиент, не пользовавшийся ничем, в отчёте о расходе — шум. Но «ничем»
    # теперь означает ноль по ВСЕМ трём метрикам, а не по одной.
    items = [
        row for row in rows if row.doc_generations or row.storage_bytes or row.active_workers
    ]
    return FleetUsageReport(
        period=yyyymm,
        items=items,
        total_doc_generations=sum(row.doc_generations for row in items),
        total_storage_bytes=sum(row.storage_bytes for row in items),
        total_active_workers=sum(row.active_workers for row in items),
        not_measured=list(NOT_MEASURED_METRICS),
    )


@router.get("/plans", response_model=PlanCatalog)
async def list_plans_endpoint(
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> PlanCatalog:
    """The subscription tier catalogue the fleet UI renders its plan picker from.

    Справочник открыт и партнёру: без названий тарифов его кабинет показывал бы
    клиентов с пустой колонкой «тариф». Это только чтение — менять тариф
    партнёр по-прежнему не может (см. ``_require_commercial_rights``).
    """

    _require_fleet_actor(credentials, tenant)
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

    _require_fleet_actor(credentials, tenant)
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

    _payload, _scope = _require_fleet_actor(credentials, tenant)
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

        # Кто кому может завести арендатора — ТЕ ЖЕ правила, что у второй двери
        # (`routes/tenants.py`). Владелец платформы может сразу отдать нового
        # арендатора партнёру; партнёру подставляется он сам, и завести
        # партнёра он не может. Своя проверка здесь однажды разошлась бы с
        # соседней, и «чей это клиент» стало бы зависеть от ручки.
        parent_record = (
            await provisioning_session.get(Tenant, payload.parent_id)
            if payload.parent_id
            else None
        )
        try:
            plan = plan_tenant_creation(
                actor=_fleet_node(tenant),
                requested_kind=payload.kind,
                requested_parent_id=payload.parent_id,
                parent=_fleet_node(parent_record) if parent_record is not None else None,
                managing_slug=get_settings().managing_tenant_slug,
            )
        except HierarchyViolation as exc:
            raise hierarchy_http_error(exc, error_type="platform-tenants") from exc

        # Отрасль проверяется ЗДЕСЬ, до выдачи: неизвестный код на середине
        # bootstrap оставил бы за собой схему в базе и половину справочников.
        try:
            resolve_industry(payload.industry)
        except UnknownIndustryError as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=api_problem_detail(
                    code="UNKNOWN_INDUSTRY",
                    message=(
                        f"{exc}. Доступные: "
                        + ", ".join(item.code for item in INDUSTRIES)
                    ),
                    error_type="platform-tenants",
                ),
            ) from exc

        # Тариф — тоже до выдачи и по тому же доводу (BIZ-53 разд. 53.1).
        if payload.plan is not None and payload.plan not in PLANS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=api_problem_detail(
                    code="UNKNOWN_PLAN",
                    message=(
                        f"Неизвестный тариф {payload.plan!r}. Доступные: "
                        + ", ".join(PLANS)
                    ),
                    error_type="platform-tenants",
                ),
            )

        service = BootstrapTenantService(provisioning_session)
        try:
            summary = await service.run(
                tenant_slug=slug,
                tenant_name=payload.name.strip(),
                owner_email=str(payload.owner_email),
                owner_password=payload.owner_password,
                demo=payload.demo_data,
                parent_id=plan.parent_id,
                industry=payload.industry,
                plan_code=payload.plan,
            )
            created = (
                await provisioning_session.execute(select(Tenant).where(Tenant.slug == slug))
            ).scalar_one()
            # Вид — тоже из решения правил, а не из тела: партнёр не заведёт
            # партнёра даже подменой поля в запросе.
            if plan.kind != created.kind:
                created.kind = plan.kind
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


@router.patch("/{tenant_id}/status", response_model=TenantStatusResult)
@audit_operation("update_status", "tenant")
async def patch_tenant_status_endpoint(
    tenant_id: str,
    payload: TenantStatusPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantRead:
    """Enable or suspend a tenant — the subscription on/off switch.

    Приостановка клиента — обычная работа партнёра, поэтому она открыта и ему,
    но только в своём поддереве. Себя партнёр приостановить не может: он не
    входит в собственную область (см. ``is_in_scope``), иначе одним запросом
    запер бы собственный кабинет.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)
    # Suspending the managing tenant would lock everyone out of fleet management.
    if target.slug.strip().lower() == get_settings().managing_tenant_slug:
        raise HTTPException(status.HTTP_409_CONFLICT, "Managing tenant cannot be suspended")

    # SEC-63.1, четвёртая угроза («каскадное отключение как оружие»): ТЗ требует
    # АУДИТ КАСКАДА. Считаем затронутых ДО записи — после неё уже не отличить,
    # кого задело именно этим действием.
    impact = await _cascade_impact(session, target)

    target.is_active = payload.is_active
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(target)

    if impact.is_reseller:
        # Отдельная запись рядом с `update_status`: та отвечает «что стало со
        # строкой», эта — «кого это задело». Без второй нельзя ни предупредить
        # заранее, ни доказать потом, что данные клиентов не тронуты.
        await _log_cascade(
            session,
            actor=tenant,
            target=target,
            impact=impact,
            activating=payload.is_active,
        )

    return TenantStatusResult(
        **TenantRead.model_validate(target).model_dump(),
        cascade_affected=list(impact.affected),
        cascade_summary=impact.summary,
    )


def _pack_file_for(target: Tenant) -> tuple[str, dict | None]:
    """Файл эталона, которым разворачивали этого клиента, и его содержимое.

    Имя набора берётся из слепка: клиента могли завести отраслью, и предлагать
    ему обновления ОБЩЕГО набора значило бы подсунуть чужие строки.
    """

    applied = None
    settings_blob = target.settings if isinstance(target.settings, dict) else {}
    stored = settings_blob.get("starter_pack")
    if isinstance(stored, dict):
        applied = stored
    pack = str((applied or {}).get("pack") or "default")
    path = STARTER_PACK_ROOT / "v1" / f"{pack}.json"
    if not path.exists():
        return pack, None
    return pack, json.loads(path.read_text(encoding="utf-8"))


async def _pack_update_for(target: Tenant) -> tuple[str, PackUpdate, dict | None]:
    pack, current = _pack_file_for(target)
    if current is None:
        # Файла нет — предлагать нечего. Это не ошибка запроса: набор мог быть
        # снят из репозитория, а клиент продолжает работать.
        empty = plan_pack_update(applied=None, current={})
        return pack, empty, None
    settings_blob = target.settings if isinstance(target.settings, dict) else {}
    applied = settings_blob.get("starter_pack")
    update = plan_pack_update(
        applied=applied if isinstance(applied, dict) else None, current=current
    )
    return pack, update, current


@router.get("/{tenant_id}/pack-update", response_model=PackUpdatePreview)
async def preview_pack_update(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> PackUpdatePreview:
    """Что нового в эталоне у этого клиента (разд. 52.3).

    Набор применяется ОДИН раз — при выдаче арендатора, — а дальше эталон живёт
    своей жизнью. Партнёр, добавивший в набор новую опасность, доносил её только
    до НОВЫХ клиентов; у прежних она не появлялась никогда, и узнать об этом
    было неоткуда.

    Сравнение идёт с ПРИМЕНЁННЫМ слепком, а не с текущими справочниками: строку,
    которую клиент осознанно удалил, обновление не воскресит.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)
    pack, update, _current = await _pack_update_for(target)
    return PackUpdatePreview(
        pack=pack,
        applied_revision=update.applied_revision,
        current_revision=update.current_revision,
        additions=dict(update.additions),
        applied_unknown=update.applied_unknown,
        summary=update.summary,
    )


@router.post("/{tenant_id}/pack-update", response_model=PackUpdateResult)
@audit_operation("apply", "tenant_pack_update")
async def apply_pack_update(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> PackUpdateResult:
    """Принять обновление эталона (разд. 52.3).

    Применяются ТОЛЬКО добавления: удаление строк из эталона не превращается в
    удаление у клиента — он мог построить на них свою работу, а «обновление
    набора» не то действие, после которого данные исчезают.

    После применения слепок в настройках заменяется текущим: иначе следующий
    вызов предложил бы то же самое ещё раз.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)
    pack, update, current = await _pack_update_for(target)

    result = PackUpdateResult(
        pack=pack,
        applied_revision=update.applied_revision,
        current_revision=update.current_revision,
        additions=dict(update.additions),
        applied_unknown=update.applied_unknown,
        summary=update.summary,
    )
    if current is None or not update.has_updates:
        return result

    async with _fleet_session() as provisioning_session:
        service = BootstrapTenantService(provisioning_session)
        summary = await service.apply_config(
            tenant_id=target.id, payload={"reference_data": update.additions}
        )
        stored = (
            await provisioning_session.execute(select(Tenant).where(Tenant.id == target.id))
        ).scalar_one()
        stored.settings = {**(stored.settings or {}), "starter_pack": current}
        await provisioning_session.commit()

    result.warnings = list(summary.warnings)
    result.applied = True
    return result


@router.get("/{tenant_id}/config", response_model=TenantConfigExport)
async def export_tenant_config(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantConfigExport:
    """Снять слепок настроек клиента (разд. 52.3).

    Срезы 7 и 12 научили РАЗВОРАЧИВАТЬ клиента с наполнением — из файла эталона.
    Обратной дороги не было: партнёр, донастроивший клиента под свою практику, не
    мог повторить это на следующем, и каждый новый донастраивался руками заново.

    Выгружаются СПРАВОЧНИКИ, а не данные: должности, опасности, меры. Люди,
    документы и медосмотры — данные клиента, их перенос называется переводом
    контура (BIZ-49) и делается совсем иначе.

    Формат тот же, что у эталонного набора: выгрузку можно положить в
    `seed/tenant_starter_packs/v1/` и получить отраслевой набор.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)

    positions = list(
        (
            await session.execute(
                select(Position.name)
                .where(Position.tenant_id == target.id, Position.deleted_at.is_(None))
                .order_by(Position.created_at.asc())
            )
        ).scalars()
    )
    hazards = list(
        (
            await session.execute(
                select(Hazard.name)
                .where(Hazard.tenant_id == target.id, Hazard.deleted_at.is_(None))
                .order_by(Hazard.created_at.asc())
            )
        ).scalars()
    )
    controls = list(
        (
            await session.execute(
                select(RiskMeasure.name)
                .where(RiskMeasure.tenant_id == target.id, RiskMeasure.deleted_at.is_(None))
                .order_by(RiskMeasure.created_at.asc())
            )
        ).scalars()
    )

    config = build_config(
        positions=positions, hazards=hazards, controls=controls, source_slug=target.slug
    )
    return TenantConfigExport.model_validate(config.as_payload(pack=target.slug))


@router.post("/{tenant_id}/config", response_model=TenantConfigApplyResult)
@audit_operation("apply", "tenant_config")
async def apply_tenant_config(
    tenant_id: str,
    payload: TenantConfigApplyRequest,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantConfigApplyResult:
    """Перенести набор на существующего клиента (разд. 52.3).

    **Добавляет, а не заменяет.** Клиент мог завести своё, и «применить
    конфигурацию» не должно означать «стереть то, что человек уже сделал».
    Посев идёт тем же кодом, что и выдача нового арендатора, и идемпотентен по
    названию: повторный перенос ничего не удваивает.

    `dry_run` показывает, что появится, не меняя ничего: перенос вслепую на
    чужой арендатор — не та операция, которую делают на ощупь.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)

    check = check_config({"reference_data": payload.reference_data})
    result = TenantConfigApplyResult(
        applicable={kind: len(values) for kind, values in check.applicable.items()},
        skipped=list(check.skipped),
        unknown=list(check.unknown),
    )
    if payload.dry_run or check.is_empty:
        return result

    async with _fleet_session() as provisioning_session:
        service = BootstrapTenantService(provisioning_session)
        summary = await service.apply_config(
            tenant_id=target.id,
            payload={"reference_data": check.applicable},
        )
    result.warnings = list(summary.warnings)
    result.applied = True
    return result


@router.get("/{tenant_id}/cascade", response_model=TenantCascadePreview)
async def preview_cascade(
    tenant_id: str,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantCascadePreview:
    """Кого затронет приостановка — ДО того, как её сделали (SEC-63.1).

    ТЗ называет каскад «оружием»: приостановка партнёра тихо переводит его
    клиентов в режим чтения. Раньше оператор узнавал об этом только по жалобам
    клиентов. Область та же, что у остальных ручек: чужой арендатор — 404.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    target = await _load_in_scope(session, tenant_id, scope)
    impact = await _cascade_impact(session, target)
    return TenantCascadePreview(
        tenant_id=target.id,
        slug=target.slug,
        is_reseller=impact.is_reseller,
        cascade_affected=list(impact.affected),
        cascade_summary=impact.summary,
    )


async def _cascade_impact(session: AsyncSession, target: Tenant) -> CascadeImpact:
    """Кого затронет смена статуса. Дети читаются одним запросом."""

    children = [
        TenantNode(id=row[0], slug=row[1], kind=row[2], parent_id=row[3], is_active=bool(row[4]))
        for row in (
            await session.execute(
                select(Tenant.id, Tenant.slug, Tenant.kind, Tenant.parent_id, Tenant.is_active)
                .where(Tenant.parent_id == target.id)
            )
        ).all()
    ]
    return plan_suspension_cascade(
        _fleet_node(target), children=children, activating=bool(target.is_active)
    )


async def _log_cascade(
    session: AsyncSession,
    *,
    actor: Tenant,
    target: Tenant,
    impact: CascadeImpact,
    activating: bool,
) -> None:
    """Записать след каскада.

    Пишется даже когда затронутых НОЛЬ: «партнёр приостановлен, клиентов нет» —
    такой же факт, как и «задето пятеро», и отсутствие записи в этом случае
    читалось бы как «мы не считали».
    """

    await AuditService(session).log_event(
        tenant_id=actor.id,
        action="tenant.suspension_cascade",
        object_type="tenant",
        object_id=target.id,
        user_id=None,
        ip="",
        details={
            "target_slug": target.slug,
            "activating": activating,
            "affected_count": impact.count,
            "affected_slugs": list(impact.affected),
            "summary": impact.summary,
        },
    )


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

    _payload, scope = _require_fleet_actor(credentials, tenant)
    _require_commercial_rights(scope)
    await _load_in_scope(session, tenant_id, scope)
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
    """Move a tenant onto a subscription tier: unlock its features and set its quotas.

    BIZ-52 срез-8: тариф клиента теперь меняет и ПАРТНЁР — в пределах своего
    набора модулей (разд. 52.4, «reseller тарифицирует своих клиентов»).
    Ограничение среза-2 (`FLEET_COMMERCIALS_PLATFORM_ONLY`) было временной
    подпоркой ровно до появления потолка; квоты остались за владельцем
    платформы — там потолок требует продуктового решения, а не кода.
    """

    _payload, scope = _require_fleet_actor(credentials, tenant)
    plan = PLANS.get(payload.plan.strip().lower())
    if plan is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown plan '{payload.plan}'",
        )
    target = await _load_in_scope(session, tenant_id, scope)
    await _enforce_plan_ceiling(scope, tenant, plan)

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

    _payload, scope = _require_fleet_actor(credentials, tenant)
    _require_commercial_rights(scope)
    target = await _load_in_scope(session, tenant_id, scope)
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

    _payload, scope = _require_fleet_actor(credentials, tenant)
    _require_commercial_rights(scope)
    target = await _load_in_scope(session, tenant_id, scope)
    if code not in FEATURE_CATALOG:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown module '{code}'")
    if not await revoke_module_trial(target, code):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"У арендатора нет пробного доступа к модулю '{code}'",
        )
    return ModuleTrialResult(code=code, title=FEATURE_CATALOG[code], trial_until=None)
