"""Rules-engine API (P10-10 срез-1): CRUD правил / каталог событий / dry-run / test / журнал.

За фичефлагом ``rules_engine`` (default-off → 404, паттерн report_builder/api.py).
RBAC: только admin/owner — правила исполняют действия от имени системы.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.role_labels import role_options
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.models.models import Tenant
from app.modules.rules_engine.actions import ActionsError
from app.modules.rules_engine.catalog import event_catalog
from app.modules.rules_engine.conditions import ConditionsError
from app.modules.rules_engine.schemas import (
    AutomationRuleCreate,
    AutomationRulePage,
    AutomationRuleRead,
    AutomationRuleUpdate,
    DryRunIn,
    DryRunOut,
    EventFieldMeta,
    EventTypeMeta,
    EventTypePage,
    RecipientRoleOption,
    RecipientRolePage,
    RuleLibraryDiscipline,
    RuleLibraryInstallOut,
    RuleLibraryPage,
    RuleTestIn,
    RuleTestOut,
    TriggerPage,
    TriggerRead,
)
from app.modules.rules_engine.service import (
    RuleNameConflict,
    RuleNotFound,
    RulesConfigError,
    RulesEngineService,
)
from app.services.audit import AuditService
from app.services.rules_library_seed import (
    install_rule_library,
    library_coverage,
    library_size,
    library_state,
)

router = APIRouter(prefix="/rules", tags=["rules-engine"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ROLES, action="manage automation rules")),
]

_FEATURE_CODE = "rules_engine"


async def _require_feature(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
) -> None:
    # BIZ-61 разд. 61.2 «безопасное выключение»: отключённый (но выдававшийся)
    # модуль читается, мутации — 403 словами; никогда не выдававшийся — 404.
    enabled = await is_module_enabled(session, str(tenant.id), _FEATURE_CODE)
    if not enabled:
        await raise_for_disabled_module(
            session,
            str(tenant.id),
            _FEATURE_CODE,
            request.method,
            error_type="rules_engine",
            disabled_code="RULES_ENGINE_DISABLED",
            disabled_message="Rules engine feature is not enabled for this tenant",
        )


FeatureGate = Depends(_require_feature)


def _error(code: str, message: str) -> dict:
    return api_problem_detail(code=code, message=message, error_type="rules_engine")


def _not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail=_error("RULE_NOT_FOUND", "Automation rule not found")
    )


def _config_error(exc: RulesConfigError | ConditionsError | ActionsError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=_error(exc.code, exc.message or str(exc)),
    )


def _audit_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _audit(
    session: AsyncSession,
    request: Request,
    access: AccessContext,
    tenant_id: str,
    *,
    action: str,
    object_id: str,
    details: dict | None = None,
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type="automation_rule",
        object_id=object_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


# ВАЖНО: статические пути объявлены ДО /{rule_id} — иначе "event-types"/"triggers"
# матчатся как rule_id.


@router.get("/event-types", response_model=EventTypePage, dependencies=[FeatureGate])
async def list_event_types(tenant: TenantDep, access: Access) -> EventTypePage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    items = [
        EventTypeMeta(
            event_type=entry["event_type"],
            fields=[EventFieldMeta(name=f["name"], kind=f["kind"]) for f in entry["fields"]],
        )
        for entry in event_catalog()
    ]
    return EventTypePage(items=items, total=len(items))


@router.get("/recipient-roles", response_model=RecipientRolePage, dependencies=[FeatureGate])
async def list_recipient_roles(tenant: TenantDep, access: Access) -> RecipientRolePage:
    """Роли, которым правило может адресовать уведомление (срез-148).

    Исполнитель принимает любую роль ``RoleEnum`` (``_KNOWN_ROLES``), а форма
    до среза держала свой список из пяти ролей со своими подписями: правила
    самой библиотеки адресованы экологу и инженеру ПБ, которых в форме не было
    — человек не видел получателя и не мог его выбрать. Список — единый
    словарь ``app.core.role_labels`` без псевдонимов, в порядке ``RoleEnum``;
    совпадение с ``_KNOWN_ROLES`` стережёт ``tests/api/test_rules_engine_actions.py``.
    """
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    items = [RecipientRoleOption(**item) for item in role_options()]
    return RecipientRolePage(items=items, total=len(items))


@router.get("/library", response_model=RuleLibraryPage, dependencies=[FeatureGate])
async def rule_library(tenant: TenantDep, session: SessionDep, access: Access) -> RuleLibraryPage:
    """Библиотека предустановленных правил по дисциплинам (разд. 57.3).

    Показывает и то, что есть, и то, чего НЕТ с причиной. До среза-62 у
    экологии, ГО-ЧС и БДД в продукте не было ни одного события, и правило для
    них пришлось бы вешать на свободный текст — то есть на угадайку; ноль без
    объяснения прочитали бы как недоделку, а не как решение. С среза-62 все
    восемь дисциплин с правилами (событие ``DisciplineDeadlineOverdue``), а
    причина остаётся обязательной на случай, если клетка снова опустеет.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    alive, deleted = await library_state(session, tenant_id=str(tenant.id))
    return RuleLibraryPage(
        items=[
            RuleLibraryDiscipline(**row) for row in library_coverage(alive=alive, deleted=deleted)
        ],
        total=library_size(),
        installed=len(alive),
        removed=len(deleted),
    )


@router.post(
    "/library/install",
    response_model=RuleLibraryInstallOut,
    dependencies=[FeatureGate],
)
async def install_library(
    request: Request, tenant: TenantDep, session: SessionDep, access: Access
) -> RuleLibraryInstallOut:
    """Выдать арендатору недостающие правила библиотеки (срез-63).

    Библиотека растёт (срез-62 добавил шесть правил по срокам дисциплин), а
    посев шёл только при создании арендатора — у существующих новые правила не
    появлялись. Ручка идемпотентна по имени: повторный вызов ничего не плодит.
    Удалённые специалистом правила НЕ возвращаются и называются в ответе
    отдельно — удаление было решением, а не потерей.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    outcome = await install_rule_library(session, tenant_id=str(tenant.id))
    if outcome.created:
        await _audit(
            session,
            request,
            access,
            str(tenant.id),
            action="library_install",
            object_id=str(tenant.id),
            details={
                "created": list(outcome.created),
                "kept_deleted": list(outcome.kept_deleted),
            },
        )
        await session.commit()
        # commit() drops the transaction-local RLS GUCs — re-arm before
        # further session work (SEC-65)
        await rearm_session_tenant_context(session)
    return RuleLibraryInstallOut(
        created=list(outcome.created),
        kept_deleted=list(outcome.kept_deleted),
        installed=outcome.installed,
        total=outcome.total,
    )


@router.get("", response_model=AutomationRulePage, dependencies=[FeatureGate])
async def list_rules(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await RulesEngineService(session, str(tenant.id)).list_rules(
        limit=limit, offset=offset
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[("total", total), ("limit", limit), ("offset", offset)],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return AutomationRulePage(
        items=[AutomationRuleRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/triggers", response_model=TriggerPage, dependencies=[FeatureGate])
async def list_triggers(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    rule_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> TriggerPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await RulesEngineService(session, str(tenant.id)).list_triggers(
        rule_id=rule_id, limit=limit, offset=offset
    )
    return TriggerPage(
        items=[TriggerRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/dry-run", response_model=DryRunOut, dependencies=[FeatureGate])
async def dry_run_rule(
    payload: DryRunIn,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DryRunOut:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        return await RulesEngineService(session, str(tenant.id)).dry_run(payload)
    except (RulesConfigError, ConditionsError, ActionsError) as exc:
        raise _config_error(exc) from exc


@router.post(
    "",
    response_model=AutomationRuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_rule(
    request: Request,
    payload: AutomationRuleCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> AutomationRuleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RulesEngineService(session, str(tenant.id))
    try:
        record = await service.create_rule(payload)
    except (RulesConfigError, ConditionsError, ActionsError) as exc:
        raise _config_error(exc) from exc
    except RuleNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("RULE_NAME_EXISTS", f"Rule name already exists: {payload.name}"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="create", object_id=record.id)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return AutomationRuleRead.model_validate(record)


@router.get("/{rule_id}", response_model=AutomationRuleRead, dependencies=[FeatureGate])
async def get_rule(
    rule_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> AutomationRuleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        record = await RulesEngineService(session, str(tenant.id)).get_rule(rule_id)
    except RuleNotFound as exc:
        raise _not_found() from exc
    return AutomationRuleRead.model_validate(record)


@router.patch("/{rule_id}", response_model=AutomationRuleRead, dependencies=[FeatureGate])
async def update_rule(
    request: Request,
    rule_id: str,
    payload: AutomationRuleUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> AutomationRuleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = RulesEngineService(session, str(tenant.id))
    try:
        record = await service.update_rule(rule_id, payload)
    except RuleNotFound as exc:
        raise _not_found() from exc
    except (RulesConfigError, ConditionsError, ActionsError) as exc:
        raise _config_error(exc) from exc
    except RuleNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("RULE_NAME_EXISTS", "Rule name already exists"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="update", object_id=record.id)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return AutomationRuleRead.model_validate(record)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[FeatureGate])
async def delete_rule(
    request: Request,
    rule_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await RulesEngineService(session, str(tenant.id)).delete_rule(rule_id)
    except RuleNotFound as exc:
        raise _not_found() from exc
    await _audit(session, request, access, str(tenant.id), action="delete", object_id=rule_id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/test", response_model=RuleTestOut, dependencies=[FeatureGate])
async def test_rule(
    rule_id: str,
    payload: RuleTestIn,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> RuleTestOut:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        return await RulesEngineService(session, str(tenant.id)).test_rule(
            rule_id, limit=payload.limit
        )
    except RuleNotFound as exc:
        raise _not_found() from exc
