"""Endpoints ведения клиентов аутсорсером (BIZ-49 срез-1, разд. 49.1–49.2).

Портфель — не «просто список»: разд. 49.2 требует видеть по всем клиентам сразу
статус договора, режим ведения и ближайшие сроки. Сводка считается ПО ВСЕМУ
портфелю, а не по странице: «активных 3» на второй странице из пяти — ложь,
за которой руководитель проектов принимает решения.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled, raise_for_disabled_module
from app.core.security import AccessContext, AuthContext, abac, get_auth_ctx, rbac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.access import (
    AccessGrant,
    AccessGrantError,
    is_grant_active,
    validate_grant,
)
from app.domains.managed_clients.attention import AggregationStatus, Severity
from app.domains.managed_clients.attention_service import (
    DEDICATED_REASON,
    collect_portfolio_attention,
)
from app.domains.managed_clients.audit_report_service import run_tenant_audit
from app.domains.managed_clients.calendar import CalendarFilters, DeadlineKind, group_by_date
from app.domains.managed_clients.calendar_service import collect_portfolio_deadlines
from app.domains.managed_clients.change_feed import (
    ChangeStatus,
    ChangeSummary,
    ClientChangeKind,
    suggestions_for,
    title_for,
)
from app.domains.managed_clients.consent import (
    ClientConsent,
    ConsentInvalid,
    require_active_consent,
    validate_consent,
)
from app.domains.managed_clients.context import (
    ClientContextDenied,
    build_context_audit_meta,
    resolve_client_context,
)
from app.domains.managed_clients.impersonation import (
    session_expires_at,
    session_seconds_left,
)
from app.domains.managed_clients.lifecycle import (
    ContractStatus,
    ManagedClientMode,
    ManagedClientTransitionError,
    contract_days_left,
    is_contract_expiring,
    validate_contract_transition,
    validate_conversion_to_dedicated,
    validate_mode_binding,
)
from app.domains.managed_clients.readiness import build_directions, worst_light
from app.domains.managed_clients.readiness_service import collect_client_numbers
from app.domains.managed_clients.scope import scoped_section_titles
from app.domains.managed_clients.session_service import (
    close_open_sessions,
    close_open_sessions_for_client,
)
from app.domains.managed_clients.transfer import (
    TransferError,
    validate_transfer_preconditions,
)
from app.domains.managed_clients.transfer_service import (
    copy_client_history,
    copy_company_with_people,
    copy_documents,
    copy_norms,
    copy_person_domains,
    copy_training_history,
    count_left_behind,
)
from app.domains.managed_clients.workload import DEFAULT_THRESHOLDS, OVERLOAD_REASON_TEXT
from app.domains.managed_clients.workload_service import collect_specialist_workload
from app.domains.reseller import TenantNode, inherited_parent_for_spawned_tenant
from app.models.audit_log import AuditLog
from app.models.client_changes import ClientAuditReport, ClientChange
from app.models.identity import User
from app.models.managed_clients import (
    ManagedClient,
    ManagedClientAccess,
    ManagedClientConsent,
    ManagedClientContextSession,
    ManagedClientTransfer,
)
from app.models.tenant_billing import RoleEnum
from app.models.tenanting import Tenant
from app.modules.audit.writer import write_audit_event
from app.schemas.managed_clients import (
    AccessGrantCreate,
    AccessGrantRead,
    AttentionSignalRead,
    AuditRunRead,
    CalendarSummary,
    ClientAccessLogEntry,
    ClientAccessLogPage,
    ClientAttentionRead,
    ClientAuditReportPage,
    ClientAuditReportRead,
    ClientChangeCreate,
    ClientChangePage,
    ClientChangeRead,
    ClientChangeStatusPatch,
    ClientContextRead,
    ClientContourSession,
    ClientReadinessRead,
    ConsentCreate,
    ConsentRead,
    ConsentRevoke,
    ConversionRead,
    ConvertToDedicated,
    CrossClientAttentionResponse,
    CrossClientAttentionSummary,
    CrossClientCalendarResponse,
    DeadlineDayRead,
    DeadlineEventRead,
    DirectionReadinessRead,
    DqSignalsRead,
    ManagedClientCreate,
    ManagedClientRead,
    ManagedClientUpdate,
    MyManagedClient,
    MyManagedClientsResponse,
    OverloadReasonRead,
    PortfolioItem,
    PortfolioPage,
    PortfolioSummary,
    ReportSendRead,
    SpecialistWorkloadRead,
    SpecialistWorkloadResponse,
    TransferRead,
    WorkloadSummary,
    WorkloadThresholdsRead,
)
from app.services.client_change_signals import enqueue_change_recorded
from app.services.client_dq_signals import DqSignalsOutcome, collect_dq_signals
from app.services.client_report_mail import ReportSendStatus, send_report_to_client
from app.services.discipline_applicability import collect_applicability, only_applicable
from app.services.managed_client_contour import close_contour_session, open_contour_session
from app.services.tenants.bootstrap.service import BootstrapTenantService

router = APIRouter(prefix="/managed-clients", tags=["managed-clients"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Портфель ведёт руководитель проектов аутсорсера; линейным ролям он не нужен
# и показывал бы им коммерческие данные чужих клиентов.
_ROLES = ["admin", "owner", "manager", "ot_pb_lead"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]
# «Мои клиенты» доступны ЛЮБОМУ аутентифицированному специалисту арендатора:
# это личная выборка, а не обзор портфеля. Пустой список ролей = только
# аутентификация; она же кладёт access_context, из которого get_auth_ctx
# берёт субъекта (без неё роут отвечал 401 при валидном токене).
AnyAuthenticated = Annotated[AccessContext, Depends(abac(_tenant_resource_id))]

_FEATURE_CODE = "managed_clients"

#: Горизонт сигнала «договор истекает» в портфеле.
CONTRACT_EXPIRY_HORIZON_DAYS = 30


def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


async def _require_enabled(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    # Аутентификация РАНЬШЕ гейта: без токена ответ обязан быть 401 (редирект
    # на вход), а не 404 модуля — прежний порядок «auth в эндпоинте, гейт в
    # теле» давал именно это, роутерная зависимость обязана его сохранить.
    _access: AccessContext = Depends(rbac(None)),
) -> None:
    """Гейт модуля — роутерная зависимость (каждый эндпоинт роутера).

    BIZ-61 разд. 61.2 «безопасное выключение»: отключённый (но выдававшийся)
    модуль читается, мутации — 403 словами; никогда не выдававшийся — 404.
    """

    enabled = await is_module_enabled(session, str(tenant.id), _FEATURE_CODE)
    if not enabled:
        await raise_for_disabled_module(
            session,
            str(tenant.id),
            _FEATURE_CODE,
            request.method,
            error_type="managed_clients",
            disabled_code="MANAGED_CLIENTS_DISABLED",
            disabled_message="Managed clients module is not enabled for this tenant",
        )


# Зависимость роутера регистрируется ДО объявления эндпоинтов ниже по файлу.
router.dependencies.append(Depends(_require_enabled))


def _err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=code, message=message, error_type="managed_clients"),
    )


def _invalid(exc: ManagedClientTransitionError) -> HTTPException:
    return _err("MANAGED_CLIENT_MODE_INVALID", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)


def _context_denied(message: str) -> HTTPException:
    """Отказ входа в контекст: 403 вместо тихого игнорирования заявки."""

    return _err("MANAGED_CLIENT_CONTEXT_DENIED", message, status.HTTP_403_FORBIDDEN)


def _conflict(exc: ManagedClientTransitionError) -> HTTPException:
    return _err("MANAGED_CLIENT_TRANSITION_INVALID", str(exc), status.HTTP_409_CONFLICT)


async def _get(session: AsyncSession, tenant: Tenant, mcid: str) -> ManagedClient:
    row = (
        await session.execute(
            select(ManagedClient).where(
                ManagedClient.id == mcid,
                ManagedClient.tenant_id == tenant.id,
                ManagedClient.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Managed client not found")
    return row


def _to_item(row: ManagedClient, *, today: date) -> PortfolioItem:
    return PortfolioItem(
        **ManagedClientRead.model_validate(row, from_attributes=True).model_dump(),
        contract_days_left=contract_days_left(row.contract_ends_at, today=today),
        contract_expiring=is_contract_expiring(
            row.contract_status,
            row.contract_ends_at,
            today=today,
            horizon_days=CONTRACT_EXPIRY_HORIZON_DAYS,
        ),
    )


def _as_grant(row: ManagedClientAccess) -> AccessGrant:
    return AccessGrant(
        client_id=row.managed_client_id,
        user_id=row.user_id,
        all_modules=bool(row.all_modules),
        modules=tuple(row.modules or ()),
        revoked_at=row.revoked_at,
    )


def _grant_read(row: ManagedClientAccess, *, now: datetime) -> AccessGrantRead:
    return AccessGrantRead(
        id=row.id,
        managed_client_id=row.managed_client_id,
        user_id=row.user_id,
        all_modules=bool(row.all_modules),
        modules=list(row.modules or []),
        granted_by_user_id=row.granted_by_user_id,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
        active=is_grant_active(_as_grant(row), now=now),
    )


def _trusted_session() -> AsyncSession:
    """Доверенная сессия для межарендаторной фазы перевода (SEC-65).

    Перевод пишет в ДВА арендатора: bootstrap нового (tenant, настройки, квота,
    владелец) и строку клиента в пространстве аутсорсера. Сессия запроса
    приколота к арендатору аутсорсера, и под FORCE RLS её WITH CHECK отвергает
    чужие строки — на SQLite это невидимо, на Postgres перевод падал бы.
    Авторизация проверена ДО вызова (роли Access + флаг модуля) — тот же
    приём, что у платформенных ручек аренды (platform_tenants).
    """

    # schema_name="public" ЯВНО: с одним tenant="public" схема выводится как
    # несуществующая tenant_public, и search_path остаётся пустым — тогда
    # неквалифицированные enum-касты (INSERT tenant ... ::tenantkind) падают
    # «type does not exist», хотя тип на месте (поймано PG-тестом перевода).
    return AsyncSessionLocal(
        tenant="public",
        schema_name="public",
        include_public=False,
        create_schema=False,
        rls_bypass=True,
    )


def _as_consent(row: ManagedClientConsent) -> ClientConsent:
    return ClientConsent(
        client_id=row.managed_client_id,
        document_ref=row.document_ref,
        granted_at=row.granted_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


def _consent_read(row: ManagedClientConsent, *, now: datetime) -> ConsentRead:
    from app.domains.managed_clients.consent import is_consent_active

    return ConsentRead(
        id=row.id,
        managed_client_id=row.managed_client_id,
        document_ref=row.document_ref,
        granted_by_user_id=row.granted_by_user_id,
        granted_at=row.granted_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        revoked_by_user_id=row.revoked_by_user_id,
        revoke_reason=row.revoke_reason,
        active=is_consent_active(_as_consent(row), now=now),
    )


def _access_log_entry(row: AuditLog) -> ClientAccessLogEntry:
    """Строка журнала доступа из записи аудита (срез-18, Доп. №3 63.2)."""

    details: dict[str, Any] = row.details if isinstance(row.details, dict) else {}
    raw_meta = details.get("meta_json")
    meta: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
    return ClientAccessLogEntry(
        at=row.when,
        actor_user_id=row.user_id,
        actor_email=row.actor_email,
        method=meta.get("method"),
        path=meta.get("action"),
        ip=row.ip,
        correlation_id=row.correlation_id,
    )


#: Публичное имя для кабинета клиента (`routes/client_access_log.py`): он
#: показывает ТЕ ЖЕ записи у себя, и своя копия преобразования разъехалась бы —
#: «кто трогал мои данные» начало бы отвечать разное в двух кабинетах.
access_log_entry = _access_log_entry


async def _client_consents(
    session: AsyncSession, tenant: Tenant, client_id: str
) -> list[ManagedClientConsent]:
    return list(
        (
            await session.execute(
                select(ManagedClientConsent)
                .where(
                    ManagedClientConsent.tenant_id == tenant.id,
                    ManagedClientConsent.managed_client_id == client_id,
                )
                .order_by(ManagedClientConsent.granted_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def _require_client_consent(
    session: AsyncSession, tenant: Tenant, client_id: str, *, now: datetime
) -> None:
    """Срез-12: без действующего согласия клиента делегированный доступ закрыт.

    Отдельный код ошибки (как MANAGED_CLIENT_CONTEXT_EXPIRED в срезе-10):
    интерфейс должен отличать «нет согласия — принесите документ» от
    «нет доступа» и не отправлять человека выпрашивать грант, который
    ему не поможет.
    """

    rows = await _client_consents(session, tenant, client_id)
    from app.domains.managed_clients.consent import ConsentRequired

    try:
        require_active_consent([_as_consent(r) for r in rows], now=now)
    except ConsentRequired as exc:
        raise _err("MANAGED_CLIENT_CONSENT_REQUIRED", str(exc), status.HTTP_409_CONFLICT) from exc


@router.get("", response_model=PortfolioPage)
async def portfolio(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PortfolioPage | Response:
    """Портфель клиентов со сводкой (разд. 49.2, блок «Портфель клиентов»)."""

    TenantContextValidator.ensure_tenant_context(tenant)
    today = _today()

    base = select(ManagedClient).where(
        ManagedClient.tenant_id == tenant.id,
        ManagedClient.deleted_at.is_(None),
    )
    total = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one() or 0
    )
    page_rows = list(
        (await session.execute(base.order_by(ManagedClient.name.asc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    # Сводка — по ВСЕМУ портфелю: постраничная сводка вводила бы в заблуждение.
    all_rows = list((await session.execute(base)).scalars().all())
    summary = PortfolioSummary(
        total=total,
        active=sum(1 for r in all_rows if r.contract_status is ContractStatus.ACTIVE),
        draft=sum(1 for r in all_rows if r.contract_status is ContractStatus.DRAFT),
        suspended=sum(1 for r in all_rows if r.contract_status is ContractStatus.SUSPENDED),
        terminated=sum(1 for r in all_rows if r.contract_status is ContractStatus.TERMINATED),
        lightweight=sum(1 for r in all_rows if r.mode is ManagedClientMode.LIGHTWEIGHT),
        dedicated=sum(1 for r in all_rows if r.mode is ManagedClientMode.DEDICATED),
        contracts_expiring=sum(
            1
            for r in all_rows
            if is_contract_expiring(
                r.contract_status,
                r.contract_ends_at,
                today=today,
                horizon_days=CONTRACT_EXPIRY_HORIZON_DAYS,
            )
        ),
    )

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=page_rows,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("expiring", summary.contracts_expiring),
            ("today", today.isoformat()),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return PortfolioPage(
        items=[_to_item(r, today=today) for r in page_rows],
        summary=summary,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/attention", response_model=CrossClientAttentionResponse)
async def cross_client_attention(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> CrossClientAttentionResponse | Response:
    """Сводный «Центр внимания» по ВСЕМ клиентам портфеля (разд. 49.2).

    Порядок — «где горит сильнее» сверху: аутсорсер читает список сверху вниз,
    и список, отсортированный по алфавиту, бесполезен.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)
    today = _today()

    rows = await collect_portfolio_attention(
        session,
        tenant_id=str(tenant.id),
        today=today,
        now=now,
        horizon_days=CONTRACT_EXPIRY_HORIZON_DAYS,
    )
    items = [
        ClientAttentionRead(
            client_id=row.client_id,
            client_name=row.client_name,
            aggregation=row.aggregation,
            signals=[
                AttentionSignalRead(
                    kind=s.kind,
                    count=s.count,
                    severity=s.severity,
                    title=s.title,
                    action_hint=s.action_hint,
                )
                for s in row.signals
            ],
            total=row.total,
            severity=row.severity,
            reason=row.reason,
        )
        for row in rows
    ]
    summary = CrossClientAttentionSummary(
        clients_total=len(rows),
        clients_with_signals=sum(1 for r in rows if r.signals),
        clients_not_aggregated=sum(
            1 for r in rows if r.aggregation is AggregationStatus.NOT_AGGREGATED
        ),
        signals_total=sum(r.total or 0 for r in rows),
        critical_clients=sum(1 for r in rows if r.severity is Severity.CRITICAL),
    )

    # ``compute_list_etag`` ждёт ORM-строки с id/updated_at, а здесь вычисляемая
    # проекция — поэтому состояние портфеля кладётся в скаляр-отпечаток целиком.
    digest = ";".join(
        f"{r.client_id}:{r.aggregation.value}:{r.total}:{r.severity.value if r.severity else ''}"
        for r in rows
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[],
        scalars=[
            ("clients", summary.clients_total),
            ("signals", summary.signals_total),
            ("critical", summary.critical_clients),
            ("not_aggregated", summary.clients_not_aggregated),
            ("today", today.isoformat()),
            ("digest", digest),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return CrossClientAttentionResponse(generated_at=now, summary=summary, items=items)


@router.get("/calendar", response_model=CrossClientCalendarResponse)
async def cross_client_calendar(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    days: int = Query(30, ge=1, le=365, description="Горизонт вперёд, дней"),
    client_id: str | None = Query(None, description="Фильтр по клиенту"),
    responsible_person_id: str | None = Query(None, description="Фильтр по специалисту"),
    kind: list[DeadlineKind] | None = Query(None, description="Фильтр по типу дедлайна"),
) -> CrossClientCalendarResponse | Response:
    """Единый календарь дедлайнов по всем клиентам (разд. 49.2).

    Просроченное всегда в выборке — оно и есть самое срочное; горизонт
    ограничивает только будущее.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)
    today = _today()

    events = await collect_portfolio_deadlines(
        session,
        tenant_id=str(tenant.id),
        today=today,
        horizon_days=days,
        filters=CalendarFilters(
            client_id=client_id,
            responsible_person_id=responsible_person_id,
            kinds=set(kind) if kind else None,
        ),
        now=now,
    )
    summary = CalendarSummary(
        events_total=len(events),
        overdue=sum(1 for e in events if e.overdue),
        due_today=sum(1 for e in events if e.days_left == 0),
        upcoming=sum(1 for e in events if e.days_left > 0),
        clients_touched=len({e.client_id for e in events}),
    )
    days_out = [
        DeadlineDayRead(
            due_date=group.due_date,
            overdue=group.overdue,
            events=[
                DeadlineEventRead(
                    kind=e.kind,
                    title=e.title,
                    due_date=e.due_date,
                    client_id=e.client_id,
                    client_name=e.client_name,
                    subject=e.subject,
                    responsible_person_id=e.responsible_person_id,
                    days_left=e.days_left,
                    overdue=e.overdue,
                )
                for e in group.events
            ],
        )
        for group in group_by_date(events)
    ]

    digest = ";".join(f"{e.client_id}:{e.kind.value}:{e.due_date}:{e.subject}" for e in events)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[],
        scalars=[
            ("events", summary.events_total),
            ("overdue", summary.overdue),
            ("days", days),
            ("client", client_id or ""),
            ("responsible", responsible_person_id or ""),
            ("kinds", ",".join(sorted(k.value for k in kind)) if kind else ""),
            ("today", today.isoformat()),
            ("digest", digest),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return CrossClientCalendarResponse(
        generated_at=now, horizon_days=days, summary=summary, days=days_out
    )


@router.get("/workload", response_model=SpecialistWorkloadResponse)
async def specialist_workload(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    days: int = Query(30, ge=1, le=365, description="Горизонт для просрочек, дней"),
) -> SpecialistWorkloadResponse | Response:
    """Загрузка специалистов по портфелю (разд. 49.2, блок «Загрузка специалистов»).

    Пороги перегруза возвращаются вместе с данными: строка «перегружен» без
    объяснения, по какому правилу, вызывает спор, а не действие.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)
    today = _today()

    rows = await collect_specialist_workload(
        session,
        tenant_id=str(tenant.id),
        today=today,
        horizon_days=days,
        thresholds=DEFAULT_THRESHOLDS,
        now=now,
    )
    items = [
        SpecialistWorkloadRead(
            person_id=r.person_id,
            person_name=r.person_name,
            unassigned=r.unassigned,
            clients_total=r.clients_total,
            clients_critical=r.clients_critical,
            signals_total=r.signals_total,
            overdue_deadlines=r.overdue_deadlines,
            overloaded=r.overloaded,
            overload_reasons=[
                OverloadReasonRead(code=reason, text=OVERLOAD_REASON_TEXT[reason])
                for reason in r.overload_reasons
            ],
        )
        for r in rows
    ]
    summary = WorkloadSummary(
        specialists_total=sum(1 for r in rows if not r.unassigned),
        overloaded=sum(1 for r in rows if r.overloaded and not r.unassigned),
        clients_unassigned=sum(r.clients_total for r in rows if r.unassigned),
    )

    digest = ";".join(
        f"{r.person_id}:{r.clients_total}:{r.signals_total}:{r.overdue_deadlines}:{int(r.overloaded)}"
        for r in rows
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[],
        scalars=[
            ("specialists", summary.specialists_total),
            ("overloaded", summary.overloaded),
            ("days", days),
            ("today", today.isoformat()),
            ("digest", digest),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return SpecialistWorkloadResponse(
        generated_at=now,
        thresholds=WorkloadThresholdsRead(
            max_clients=DEFAULT_THRESHOLDS.max_clients,
            max_signals=DEFAULT_THRESHOLDS.max_signals,
            max_overdue=DEFAULT_THRESHOLDS.max_overdue,
        ),
        summary=summary,
        items=items,
    )


@router.get("/my", response_model=MyManagedClientsResponse)
async def my_managed_clients(
    tenant: TenantDep,
    session: SessionDep,
    access: AnyAuthenticated,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> MyManagedClientsResponse:
    """Клиенты, доступные текущему специалисту (основа переключателя, разд. 49.3).

    Намеренно БЕЗ роли-гейта портфеля: этот список — не обзор всего портфеля,
    а личная выборка «куда мне открыт доступ». Отсутствие грантов даёт пустой
    список, а не весь портфель.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)

    rows = list(
        (
            await session.execute(
                select(ManagedClientAccess, ManagedClient)
                .join(ManagedClient, ManagedClient.id == ManagedClientAccess.managed_client_id)
                .where(
                    ManagedClientAccess.tenant_id == tenant.id,
                    ManagedClientAccess.user_id == auth.sub,
                    ManagedClient.deleted_at.is_(None),
                )
            )
        ).all()
    )
    items = [
        MyManagedClient(
            client_id=client.id,
            client_name=client.name,
            mode=client.mode,
            all_modules=grant.all_modules,
            modules=list(grant.modules or []),
        )
        for grant, client in rows
        if is_grant_active(_as_grant(grant), now=now)
    ]
    items.sort(key=lambda i: i.client_name)
    return MyManagedClientsResponse(items=items, scoped_sections=scoped_section_titles())


@router.post("/{mcid}/context", response_model=ClientContextRead)
async def enter_client_context(
    mcid: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: AnyAuthenticated,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> ClientContextRead:
    """Войти в контекст клиента — «работаю от имени этого клиента» (разд. 49.3).

    Точка входа для переключателя клиентов: проверяет грант и ФИКСИРУЕТ вход
    в аудите. Отдельные роуты данных получают тот же контекст зависимостью
    ``ClientContextDep`` по заголовку ``X-Managed-Client``.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)

    client = (
        await session.execute(
            select(ManagedClient).where(
                ManagedClient.id == mcid,
                ManagedClient.tenant_id == tenant.id,
                ManagedClient.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if client is None:
        # Тот же ответ, что и при отсутствии гранта: существование чужого
        # клиента — тоже сведения, которых спрашивающий знать не должен.
        raise _context_denied("Нет доступа к этому клиенту")

    row = (
        await session.execute(
            select(ManagedClientAccess).where(
                ManagedClientAccess.tenant_id == tenant.id,
                ManagedClientAccess.managed_client_id == client.id,
                ManagedClientAccess.user_id == auth.sub,
                ManagedClientAccess.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    try:
        context = resolve_client_context(
            grant=_as_grant(row) if row is not None else None,
            user_id=auth.sub,
            client_id=client.id,
            client_name=client.name,
            now=now,
        )
    except ClientContextDenied as exc:
        raise _context_denied(str(exc)) from exc

    # Срез-12: гранты долгоживущие, а согласие клиента может быть отозвано
    # позже выдачи — вход «от имени» перепроверяет его каждый раз.
    await _require_client_consent(session, tenant, client.id, now=now)

    # Срез-10: вход открывает СЕССИЮ со сроком. Прошлые открытые сессии этого
    # специалиста закрываются: две одновременные работы «от имени» разных
    # клиентов сделали бы журнал доступа невосстановимым — непонятно, к чьим
    # данным относится действие.
    await close_open_sessions(
        session, tenant_id=str(tenant.id), user_id=auth.sub, now=now, reason="switched"
    )
    row_session = ManagedClientContextSession(
        tenant_id=tenant.id,
        managed_client_id=client.id,
        user_id=auth.sub,
        started_at=now,
    )
    session.add(row_session)
    await session.flush()

    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.context.enter",
        resource_type="managed_client",
        resource_id=client.id,
        before=None,
        after=None,
        # Метод пишется и здесь: строка «вход в контекст» стоит в журнале
        # доступа рядом с обращениями к данным и должна читаться так же.
        meta=build_context_audit_meta(context, action="context.enter", method=request.method),
    )

    # У Dedicated-клиента данные лежат в ЕГО контуре: одного контекста мало,
    # нужен ключ от чужого арендатора. Право на него проверяется здесь и
    # целиком (иерархия + согласие), а отказ приходит ПРИЧИНОЙ, а не пустотой:
    # иначе «войти вошёл, а данных нет» читается как поломка.
    contour: ClientContourSession | None = None
    contour_reason: str | None = None
    if client.mode is ManagedClientMode.DEDICATED:
        entry, reason = await open_contour_session(
            session,
            client=client,
            outsourcer_tenant=tenant,
            specialist_user_id=auth.sub,
            now=now,
        )
        if entry is None:
            contour_reason = reason
        else:
            contour = ClientContourSession(
                tenant_slug=entry.tenant_slug,
                access_token=entry.access_token,
                role=entry.role,
                display_name=entry.display_name,
            )

    return ClientContextRead(
        scoped_sections=scoped_section_titles(),
        client_id=context.client_id,
        client_name=context.client_name,
        mode=client.mode,
        all_modules=context.all_modules,
        modules=list(context.modules),
        expires_at=session_expires_at(now),
        seconds_left=session_seconds_left(started_at=now, now=now),
        contour=contour,
        contour_reason=contour_reason,
    )


@router.delete("/context", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def leave_client_context(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: AnyAuthenticated,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> Response:
    """Выйти из контекста клиента (разд. 49.3 + Доп. №3 63.2).

    До среза-10 выход был чисто интерфейсным: баннер исчезал, а сервер об этом
    не знал — в журнале доступа работа «от имени» не имела конца. Теперь выход
    закрывает сессию и пишется в аудит.

    Идемпотентен: выйти из контекста, которого нет, — не ошибка. Иначе
    повторный клик или вкладка, открытая со вчерашним состоянием, отдавали бы
    пользователю отказ на действии, которое ничего не ломает.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    now = datetime.now(tz=timezone.utc)

    closed = await close_open_sessions(
        session, tenant_id=str(tenant.id), user_id=auth.sub, now=now, reason="left"
    )
    for row in closed:
        await write_audit_event(
            session=session,
            request=request,
            tenant_id=str(tenant.id),
            actor_id=auth.sub,
            action="managed_client.context.leave",
            resource_type="managed_client",
            resource_id=row.managed_client_id,
            before=None,
            after=None,
            meta={"on_behalf_of_client": False, "managed_client_id": row.managed_client_id},
        )
        # Выход обязан ГАСИТЬ личность в контуре клиента, иначе ключ от чужого
        # арендатора продолжал бы работать после того, как специалист вышел.
        closed_client = (
            await session.execute(
                select(ManagedClient).where(
                    ManagedClient.id == row.managed_client_id,
                    ManagedClient.tenant_id == tenant.id,
                )
            )
        ).scalar_one_or_none()
        if closed_client is not None:
            await close_contour_session(
                session,
                client=closed_client,
                outsourcer_slug=str(tenant.slug),
                specialist_user_id=auth.sub,
            )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{mcid}/access", response_model=list[AccessGrantRead])
async def list_access_grants(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[AccessGrantRead]:
    """Матрица доступа к клиенту, включая ОТОЗВАННЫЕ гранты.

    Отозванные показываются намеренно: «кто имел доступ раньше» — такой же
    вопрос безопасности, как «кто имеет сейчас».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)
    now = datetime.now(tz=timezone.utc)
    rows = list(
        (
            await session.execute(
                select(ManagedClientAccess)
                .where(
                    ManagedClientAccess.tenant_id == tenant.id,
                    ManagedClientAccess.managed_client_id == mcid,
                )
                .order_by(ManagedClientAccess.granted_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_grant_read(row, now=now) for row in rows]


@router.post("/{mcid}/access", response_model=AccessGrantRead, status_code=status.HTTP_201_CREATED)
async def grant_access(
    mcid: str,
    payload: AccessGrantCreate,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> AccessGrantRead:
    """Выдать специалисту доступ к клиенту — событие безопасности, идёт в аудит."""

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)
    # Срез-12: без действующего согласия клиента грант не выдаётся (разд. 66.3).
    await _require_client_consent(session, tenant, mcid, now=datetime.now(tz=timezone.utc))
    try:
        validate_grant(all_modules=payload.all_modules, modules=payload.modules)
    except AccessGrantError as exc:
        raise _err("MANAGED_CLIENT_ACCESS_INVALID", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)

    now = datetime.now(tz=timezone.utc)
    existing = (
        await session.execute(
            select(ManagedClientAccess).where(
                ManagedClientAccess.tenant_id == tenant.id,
                ManagedClientAccess.managed_client_id == mcid,
                ManagedClientAccess.user_id == payload.user_id,
                ManagedClientAccess.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise _err(
            "MANAGED_CLIENT_ACCESS_EXISTS",
            "У этого специалиста уже есть действующий доступ к клиенту",
            status.HTTP_409_CONFLICT,
        )

    row = ManagedClientAccess(
        tenant_id=tenant.id,
        managed_client_id=mcid,
        user_id=payload.user_id,
        all_modules=payload.all_modules,
        modules=list(payload.modules),
        granted_by_user_id=auth.sub,
        granted_at=now,
    )
    session.add(row)
    await session.flush()
    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.access.grant",
        resource_type="managed_client_access",
        resource_id=row.id,
        before=None,
        after={
            "managed_client_id": mcid,
            "user_id": payload.user_id,
            "all_modules": payload.all_modules,
            "modules": list(payload.modules),
        },
    )
    return _grant_read(row, now=now)


@router.delete("/{mcid}/access/{grant_id}", response_model=AccessGrantRead)
async def revoke_access(
    mcid: str,
    grant_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> AccessGrantRead:
    """Отозвать доступ. Строка НЕ удаляется — остаётся след «имел до»."""

    TenantContextValidator.ensure_tenant_context(tenant)
    row = (
        await session.execute(
            select(ManagedClientAccess).where(
                ManagedClientAccess.id == grant_id,
                ManagedClientAccess.tenant_id == tenant.id,
                ManagedClientAccess.managed_client_id == mcid,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Access grant not found")
    if row.revoked_at is not None:
        raise _err(
            "MANAGED_CLIENT_ACCESS_ALREADY_REVOKED",
            "Доступ уже отозван",
            status.HTTP_409_CONFLICT,
        )

    now = datetime.now(tz=timezone.utc)
    row.revoked_at = now
    row.revoked_by_user_id = auth.sub
    # Снятый грант обязан гасить и личность в контуре клиента: иначе у
    # специалиста, которого только что отключили, остался бы рабочий ключ от
    # чужого арендатора — и никто бы этого не заметил.
    revoked_client = await _get(session, tenant, mcid)
    await close_contour_session(
        session,
        client=revoked_client,
        outsourcer_slug=str(tenant.slug),
        specialist_user_id=str(row.user_id),
    )
    await session.flush()
    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.access.revoke",
        resource_type="managed_client_access",
        resource_id=row.id,
        before={"revoked_at": None},
        after={"revoked_at": now.isoformat(), "user_id": row.user_id},
    )
    return _grant_read(row, now=now)


@router.get("/{mcid}/access-log", response_model=ClientAccessLogPage)
async def client_access_log(
    mcid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientAccessLogPage:
    """Кто из специалистов и когда работал в данных этого клиента.

    Доп. №3, разд. 63.2: «клиент может запросить журнал доступа к своим
    данным». Запрос идёт через аутсорсера — у клиента в режиме Lightweight
    вообще нет учётной записи, а в Dedicated его арендатор отдельный, и следы
    работы аутсорсера физически лежат не там. Поэтому журнал отдаётся здесь,
    а показать его клиенту — обязанность аутсорсера по договору.

    Источник — записи аудита о входе в контекст: зависимость пишет такую на
    КАЖДЫЙ запрос с заголовком клиента, то есть строка журнала = одно
    обращение к данным. Что именно менялось, видно в общем аудите по
    ``correlation_id`` — эти записи с этого среза помечены «X от имени Y».

    Журнал только читается: аудит append-only, и «подчистить» его нельзя ни
    отсюда, ни откуда-либо ещё.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)

    conditions = [
        AuditLog.tenant_id == tenant.id,
        AuditLog.object_type == "managed_client",
        AuditLog.object_id == mcid,
        AuditLog.action == "managed_client.context.enter",
    ]
    if since is not None:
        conditions.append(AuditLog.when >= since)
    if until is not None:
        conditions.append(AuditLog.when <= until)

    total = int(
        (
            await session.execute(select(func.count()).select_from(AuditLog).where(*conditions))
        ).scalar_one_or_none()
        or 0
    )
    rows = (
        (
            await session.execute(
                select(AuditLog)
                .where(*conditions)
                .order_by(AuditLog.when.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ClientAccessLogPage(items=[_access_log_entry(row) for row in rows], total=total)


@router.get("/{mcid}/consents", response_model=list[ConsentRead])
async def list_client_consents(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[ConsentRead]:
    """Согласия клиента, включая ОТОЗВАННЫЕ и истёкшие.

    Прошлые согласия показываются намеренно: «действовало ли согласие, когда
    специалист работал в данных клиента» — вопрос аудита, а не истории.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)
    now = datetime.now(tz=timezone.utc)
    rows = await _client_consents(session, tenant, mcid)
    return [_consent_read(row, now=now) for row in rows]


@router.post("/{mcid}/consents", response_model=ConsentRead, status_code=status.HTTP_201_CREATED)
async def record_client_consent(
    mcid: str,
    payload: ConsentCreate,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> ConsentRead:
    """Зафиксировать согласие клиента на делегированный доступ (разд. 66.3).

    Это событие безопасности — идёт в аудит. Один и тот же документ дважды
    не записывается: даблклик не должен плодить два «основания».
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)
    now = datetime.now(tz=timezone.utc)
    try:
        validate_consent(
            document_ref=payload.document_ref, granted_at=now, expires_at=payload.expires_at
        )
    except ConsentInvalid as exc:
        raise _err(
            "MANAGED_CLIENT_CONSENT_INVALID", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY
        ) from exc

    from app.domains.managed_clients.consent import is_consent_active

    duplicate = next(
        (
            row
            for row in await _client_consents(session, tenant, mcid)
            if row.document_ref == payload.document_ref.strip()
            and is_consent_active(_as_consent(row), now=now)
        ),
        None,
    )
    if duplicate is not None:
        raise _err(
            "MANAGED_CLIENT_CONSENT_EXISTS",
            "Согласие по этому документу уже действует",
            status.HTTP_409_CONFLICT,
        )

    row = ManagedClientConsent(
        tenant_id=tenant.id,
        managed_client_id=mcid,
        document_ref=payload.document_ref.strip(),
        granted_by_user_id=auth.sub,
        granted_at=now,
        expires_at=payload.expires_at,
    )
    session.add(row)
    await session.flush()
    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.consent.grant",
        resource_type="managed_client_consent",
        resource_id=row.id,
        before=None,
        after={
            "managed_client_id": mcid,
            "document_ref": row.document_ref,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        },
    )
    return _consent_read(row, now=now)


@router.delete("/{mcid}/consents/{consent_id}", response_model=ConsentRead)
async def revoke_client_consent(
    mcid: str,
    consent_id: str,
    payload: ConsentRevoke | None,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> ConsentRead:
    """Отозвать согласие клиента — след, а не удаление.

    Отзыв немедленно ЗАКРЫВАЕТ открытые сессии работы «от имени» этого
    клиента у всех специалистов: отозванное согласие не может продолжать
    действовать до конца чьей-то сессии.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    client_row = await _get(session, tenant, mcid)
    now = datetime.now(tz=timezone.utc)
    row = (
        await session.execute(
            select(ManagedClientConsent).where(
                ManagedClientConsent.tenant_id == tenant.id,
                ManagedClientConsent.managed_client_id == mcid,
                ManagedClientConsent.id == consent_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _err(
            "MANAGED_CLIENT_CONSENT_NOT_FOUND", "Согласие не найдено", status.HTTP_404_NOT_FOUND
        )
    if row.revoked_at is not None:
        raise _err(
            "MANAGED_CLIENT_CONSENT_ALREADY_REVOKED",
            "Согласие уже отозвано",
            status.HTTP_409_CONFLICT,
        )

    row.revoked_at = now
    row.revoked_by_user_id = auth.sub
    row.revoke_reason = payload.reason if payload else None
    closed = await close_open_sessions_for_client(
        session, tenant_id=str(tenant.id), client_id=mcid, now=now, reason="consent_revoked"
    )
    # Закрыть сессию мало: у Dedicated-клиента у специалиста есть ЛИЧНОСТЬ в
    # его контуре, и она пускала бы туда своим ключом уже без согласия.
    # Согласие — основание обработки; отозвано основание — гаснет и личность.
    for closed_row in closed:
        await close_contour_session(
            session,
            client=client_row,
            outsourcer_slug=str(tenant.slug),
            specialist_user_id=str(closed_row.user_id),
        )
    await session.flush()
    await write_audit_event(
        session=session,
        request=request,
        tenant_id=str(tenant.id),
        actor_id=auth.sub,
        action="managed_client.consent.revoke",
        resource_type="managed_client_consent",
        resource_id=row.id,
        before={"document_ref": row.document_ref},
        after={
            "revoke_reason": row.revoke_reason,
            "closed_sessions": len(closed),
        },
    )
    return _consent_read(row, now=now)


@router.post("/{mcid}/convert-to-dedicated", response_model=ConversionRead)
async def convert_to_dedicated(
    mcid: str,
    payload: ConvertToDedicated,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> ConversionRead:
    """Перевод Lightweight → Dedicated (разд. 49.1) — без потери истории ядра.

    Под клиента поднимается собственный арендатор (bootstrap: настройки, квота,
    владелец, каталог прав, стартовый пакет), запись клиента переключается в
    Dedicated. Вся история ведения (договор, гранты, согласия, сессии, аудит)
    остаётся на ТОЙ ЖЕ строке клиента, а организация в пространстве аутсорсера
    остаётся ссылкой на историю (инвариант режима из среза-1). Перенос доменных
    данных организации в новый арендатор — следующий срез 49.1.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get(session, tenant, mcid)

    slug = payload.tenant_slug.strip().lower()
    try:
        validate_conversion_to_dedicated(
            mode=row.mode, contract_status=row.contract_status, target_slug=slug
        )
    except ManagedClientTransitionError as exc:
        raise _err("MANAGED_CLIENT_CONVERSION_INVALID", str(exc), status.HTTP_409_CONFLICT) from exc

    # Слаг обязан быть СВОБОДЕН: bootstrap «переиспользует» существующего
    # арендатора, а перевод в ЧУЖОЙ арендатор пришил бы клиента к чужим данным.
    taken = (await session.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if taken is not None:
        raise _err(
            "MANAGED_CLIENT_TENANT_SLUG_TAKEN",
            "Арендатор с таким слагом уже существует — перевод возможен только в новый",
            status.HTTP_409_CONFLICT,
        )

    # Фаза записи — ОДНА транзакция доверенной сессии (см. _trusted_session):
    # bootstrap нового арендатора и переключение клиента либо происходят вместе,
    # либо не происходят вовсе — «арендатор создан, а клиент не переведён»
    # оставил бы занятый слаг без владельца-клиента.
    # Новый арендатор рождается ВНУТРИ контура, где нажали кнопку (BIZ-52
    # разд. 52.1). Без этого клиент партнёра становился бы корневым арендатором —
    # то есть вставал вровень с самим партнёром и выпадал из его кабинета.
    spawned_parent_id = inherited_parent_for_spawned_tenant(
        TenantNode(
            id=tenant.id,
            slug=tenant.slug,
            kind=tenant.kind,
            parent_id=tenant.parent_id,
            is_active=bool(tenant.is_active),
        ),
        managing_slug=get_settings().managing_tenant_slug,
    )

    async with _trusted_session() as trusted:
        summary = await BootstrapTenantService(trusted).run(
            tenant_slug=slug,
            tenant_name=payload.tenant_name or row.name,
            owner_email=payload.owner_email,
            owner_password=payload.owner_password,
            parent_id=spawned_parent_id,
        )
        row_t = (
            await trusted.execute(
                select(ManagedClient).where(
                    ManagedClient.id == row.id, ManagedClient.tenant_id == tenant.id
                )
            )
        ).scalar_one()
        before = {
            "mode": row_t.mode.value,
            "dedicated_tenant_slug": row_t.dedicated_tenant_slug,
        }
        row_t.mode = ManagedClientMode.DEDICATED
        row_t.dedicated_tenant_slug = slug
        # company_id НЕ трогаем: у dedicated он законен как ссылка на историю.
        validate_mode_binding(
            row_t.mode, company_id=row_t.company_id, tenant_slug=row_t.dedicated_tenant_slug
        )
        await trusted.flush()

        await write_audit_event(
            session=trusted,
            request=request,
            tenant_id=str(tenant.id),
            actor_id=auth.sub,
            action="managed_client.converted_to_dedicated",
            resource_type="managed_client",
            resource_id=row_t.id,
            before=before,
            after={
                "mode": row_t.mode.value,
                "dedicated_tenant_slug": slug,
                "history_company_id": row_t.company_id,
                "tenant_created": list(summary.created),
            },
        )
        result = ConversionRead(
            client=ManagedClientRead.model_validate(row_t, from_attributes=True),
            tenant_slug=slug,
            tenant_created=list(summary.created),
            history_company_id=row_t.company_id,
        )
        await trusted.commit()
    return result


def _transfer_read(row: ManagedClientTransfer) -> TransferRead:
    return TransferRead(
        id=row.id,
        managed_client_id=row.managed_client_id,
        target_tenant_slug=row.target_tenant_slug,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        started_by_user_id=row.started_by_user_id,
        counts=dict(row.counts or {}),
    )


@router.get("/{mcid}/transfers", response_model=list[TransferRead])
async def list_client_transfers(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[TransferRead]:
    """Журнал переносов клиента — часть истории ведения."""

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)
    rows = (
        (
            await session.execute(
                select(ManagedClientTransfer)
                .where(
                    ManagedClientTransfer.tenant_id == tenant.id,
                    ManagedClientTransfer.managed_client_id == mcid,
                )
                .order_by(ManagedClientTransfer.started_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_transfer_read(row) for row in rows]


@router.post("/{mcid}/transfer", response_model=TransferRead)
async def transfer_client_data(
    mcid: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    auth: Annotated[AuthContext, Depends(get_auth_ctx)],
) -> TransferRead:
    """Перенос данных клиента в его арендатор (разд. 49.1, продолжение перевода).

    Копирует организацию и сотрудников; исходные строки остаются историей в
    пространстве аутсорсера, соответствие старых id новым — в журнале
    (без него «сохранение timeline» превращается в угадывание). Аудит и
    timeline не переносятся принципиально: хеш-цепочка аудита живёт в своём
    арендаторе, и переписать её в чужой значит её сломать.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get(session, tenant, mcid)

    prior = (
        (
            await session.execute(
                select(ManagedClientTransfer).where(
                    ManagedClientTransfer.tenant_id == tenant.id,
                    ManagedClientTransfer.managed_client_id == mcid,
                    ManagedClientTransfer.status == "completed",
                )
            )
        )
        .scalars()
        .first()
    )
    try:
        validate_transfer_preconditions(
            mode=row.mode,
            dedicated_tenant_slug=row.dedicated_tenant_slug,
            company_id=row.company_id,
            has_completed_transfer=prior is not None,
        )
    except TransferError as exc:
        raise _err("MANAGED_CLIENT_TRANSFER_INVALID", str(exc), status.HTTP_409_CONFLICT) from exc

    now = datetime.now(tz=timezone.utc)
    # Та же доверенная сессия, что у перевода: копии пишутся в ЧУЖОЙ арендатор,
    # и под FORCE RLS сессия запроса их не пропустит (урок фикса среза-13).
    async with _trusted_session() as trusted:
        target = (
            await trusted.execute(select(Tenant).where(Tenant.slug == row.dedicated_tenant_slug))
        ).scalar_one_or_none()
        if target is None:
            raise _err(
                "MANAGED_CLIENT_TRANSFER_TARGET_MISSING",
                "Арендатор клиента не найден — перевод не завершён или арендатор удалён",
                status.HTTP_409_CONFLICT,
            )
        result = await copy_company_with_people(
            trusted,
            source_tenant_id=str(tenant.id),
            source_company_id=row.company_id,
            target_tenant_id=str(target.id),
        )
        # Срез-15: доменная история людей — в ТОЙ ЖЕ транзакции. Раздельные
        # операции оставили бы окно, в котором люди у клиента уже есть, а их
        # медосмотры и СИЗ ещё нет: по такому состоянию клиент увидел бы
        # «никто не проходил медосмотр» и принял бы решение по пустоте.
        counts = dict(result.counts)
        counts.update(
            await copy_person_domains(
                trusted,
                source_tenant_id=str(tenant.id),
                target_tenant_id=str(target.id),
                people_map=result.people_map,
            )
        )
        counts.update(
            await copy_norms(
                trusted,
                source_tenant_id=str(tenant.id),
                target_tenant_id=str(target.id),
                position_map=result.position_map,
            )
        )
        counts.update(
            await copy_client_history(
                trusted,
                source_tenant_id=str(tenant.id),
                source_company_id=row.company_id,
                target_tenant_id=str(target.id),
                company_map=result.company_map,
                site_map=result.site_map,
                position_map=result.position_map,
                people_map=result.people_map,
            )
        )
        # Срез-19: документы клиента и их файлы. Владелец решил (2026-08-08),
        # что авторство копий записывается на ВЛАДЕЛЬЦА КЛИЕНТА: в своём
        # арендаторе документ принадлежит клиенту, а кто его готовил, видно в
        # журнале доступа (разд. 63.2). Без владельца документы не переносим —
        # приписать их первому попавшемуся пользователю значит соврать в поле,
        # которое потом читают как «кто это сделал».
        owner = (
            (
                await trusted.execute(
                    select(User)
                    .where(User.tenant_id == target.id, User.role == RoleEnum.OWNER)
                    .order_by(User.created_at.asc())
                )
            )
            .scalars()
            .first()
        )
        if owner is not None:
            counts.update(
                await copy_documents(
                    trusted,
                    source_tenant_id=str(tenant.id),
                    target_tenant_id=str(target.id),
                    target_tenant_slug=str(target.slug),
                    source_company_id=row.company_id,
                    company_map=result.company_map,
                    people_map=result.people_map,
                    site_map=result.site_map,
                    owner_user_id=str(owner.id),
                )
            )
        else:
            counts["documents_skipped_no_owner"] = 1
        counts.update(
            await copy_training_history(
                trusted,
                source_tenant_id=str(tenant.id),
                target_tenant_id=str(target.id),
                people_map=result.people_map,
            )
        )
        # Что осознанно НЕ поехало — числом: молчаливый ноль читался бы как
        # «этого у клиента не было».
        counts.update(
            await count_left_behind(
                trusted,
                source_tenant_id=str(tenant.id),
                source_company_id=row.company_id,
                people_map=result.people_map,
            )
        )
        journal = ManagedClientTransfer(
            tenant_id=tenant.id,
            managed_client_id=mcid,
            target_tenant_slug=row.dedicated_tenant_slug,
            status="completed",
            started_at=now,
            finished_at=datetime.now(tz=timezone.utc),
            started_by_user_id=auth.sub,
            counts=counts,
            id_map={"company": result.company_map, "people": result.people_map},
        )
        trusted.add(journal)
        await trusted.flush()
        await write_audit_event(
            session=trusted,
            request=request,
            tenant_id=str(tenant.id),
            actor_id=auth.sub,
            action="managed_client.data_transferred",
            resource_type="managed_client_transfer",
            resource_id=journal.id,
            before=None,
            after={
                "managed_client_id": mcid,
                "target_tenant_slug": row.dedicated_tenant_slug,
                "counts": counts,
            },
        )
        response = _transfer_read(journal)
        await trusted.commit()
    return response


@router.post("", response_model=ManagedClientRead, status_code=status.HTTP_201_CREATED)
async def create_managed_client(
    payload: ManagedClientCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> ManagedClientRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        validate_mode_binding(
            payload.mode,
            company_id=payload.company_id,
            tenant_slug=payload.dedicated_tenant_slug,
        )
    except ManagedClientTransitionError as exc:
        raise _invalid(exc)

    row = ManagedClient(
        tenant_id=tenant.id,
        name=payload.name,
        mode=payload.mode,
        company_id=payload.company_id,
        dedicated_tenant_slug=payload.dedicated_tenant_slug,
        contract_status=ContractStatus.DRAFT,
        contract_no=payload.contract_no,
        contract_starts_at=payload.contract_starts_at,
        contract_ends_at=payload.contract_ends_at,
        responsible_person_id=payload.responsible_person_id,
        notes=payload.notes,
        report_email=payload.report_email,
        report_opt_in=payload.report_opt_in,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise _err(
            "MANAGED_CLIENT_DUPLICATE",
            "Клиент с таким названием уже есть в портфеле",
            status.HTTP_409_CONFLICT,
        )
    await session.refresh(row)
    return ManagedClientRead.model_validate(row, from_attributes=True)


# --- лента изменений у клиента (BIZ-51 срез-1, Доп. №1 разд. 51.1) ---


def _change_read(row: ClientChange) -> ClientChangeRead:
    """Запись ленты вместе с тем, что по ней предлагается сделать.

    Подсказки отдаются РЯДОМ с записью, а не отдельной ручкой: список «что
    теперь делать» и есть смысл ленты, а второй запрос за ним означал бы, что
    половина интерфейсов его не сделает.
    """

    kind = ClientChangeKind(row.kind)
    return ClientChangeRead(
        id=row.id,
        kind=kind,
        kind_title=title_for(kind),
        happened_on=row.happened_on,
        summary=row.summary,
        details=row.details,
        status=ChangeStatus(row.status),
        handled_at=row.handled_at,
        suggestions=suggestions_for(kind),
        source=row.source or "manual",
    )


@router.post(
    "/{mcid}/changes", response_model=ClientChangeRead, status_code=status.HTTP_201_CREATED
)
@audit_operation("create", "client_change")
async def record_client_change(
    mcid: str,
    payload: ClientChangeCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ClientChangeRead:
    """Зафиксировать изменение у клиента (разд. 51.1).

    Разд. 51 превращает разовую услугу в подписное сопровождение: аутсорсер
    обязан отслеживать изменения у заказчика и заранее готовить документы. До
    этого среза такой ленты не было вовсе — «Центр внимания» (BIZ-49) показывает
    ПРОСРОЧКИ, то есть состояние, а принятый сотрудник или новая площадка в нём
    не появятся, пока по ним что-нибудь не просрочится.

    Запись НИЧЕГО не создаёт сама. ТЗ говорит «предложить/сделать
    автоматически», но начинать с «сделать» нельзя: одна загрузка штатки на сто
    человек породила бы сотни задач, разгребать которые пришлось бы вручную.
    Сначала специалист видит подсказки и решает.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)

    row = ClientChange(
        tenant_id=tenant.id,
        managed_client_id=mcid,
        kind=payload.kind,
        happened_on=payload.happened_on,
        summary=payload.summary.strip(),
        details=payload.details,
        status=ChangeStatus.NEW,
    )
    session.add(row)
    await session.flush()
    # Срез-9: запись ленты — событие (rules engine, вебхуки). До commit:
    # строка и событие о ней — одна транзакция.
    await enqueue_change_recorded(session, [row])
    await session.commit()
    await session.refresh(row)
    return _change_read(row)


@router.get("/{mcid}/changes", response_model=ClientChangePage)
async def list_client_changes(
    mcid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    status_filter: Annotated[ChangeStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientChangePage:
    """Лента изменений клиента: свежие сверху.

    Сводка идёт словами рядом со списком: «пусто» и «всё разобрано» — разные
    ответы, и различать их по длине списка человек не обязан.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)

    base = [
        ClientChange.tenant_id == tenant.id,
        ClientChange.managed_client_id == mcid,
        ClientChange.deleted_at.is_(None),
    ]
    listed = list(base)
    if status_filter is not None:
        listed.append(ClientChange.status == status_filter)

    total = int(
        (
            await session.execute(select(func.count()).select_from(ClientChange).where(*listed))
        ).scalar_one_or_none()
        or 0
    )
    # Счётчик «требуют внимания» считается по ВСЕЙ ленте, а не по странице:
    # иначе фильтр «разобранные» показывал бы ноль новых и успокаивал зря.
    new_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ClientChange)
                .where(*base, ClientChange.status == ChangeStatus.NEW)
            )
        ).scalar_one_or_none()
        or 0
    )
    feed_total = int(
        (
            await session.execute(select(func.count()).select_from(ClientChange).where(*base))
        ).scalar_one_or_none()
        or 0
    )
    rows = (
        (
            await session.execute(
                select(ClientChange)
                .where(*listed)
                .order_by(ClientChange.happened_on.desc(), ClientChange.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ClientChangePage(
        items=[_change_read(row) for row in rows],
        total=total,
        summary=ChangeSummary(total=feed_total, new=new_total).text,
    )


@router.patch("/{mcid}/changes/{change_id}", response_model=ClientChangeRead)
@audit_operation("update", "client_change")
async def set_client_change_status(
    mcid: str,
    change_id: str,
    payload: ClientChangeStatusPatch,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ClientChangeRead:
    """Разобрать изменение или отклонить его.

    Отклонение существует намеренно: часть изменений не требует действий
    (перевод внутри отдела без смены рабочего места), и без него лента копила бы
    вечные долги, а специалист перестал бы её открывать.

    Возврат в «новое» разрешён: специалист мог закрыть запись по ошибке, и
    единственным выходом иначе была бы вторая запись о том же изменении.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)

    row = (
        await session.execute(
            select(ClientChange).where(
                ClientChange.id == change_id,
                ClientChange.tenant_id == tenant.id,
                ClientChange.managed_client_id == mcid,
                ClientChange.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Change not found")

    row.status = payload.status
    if payload.status is ChangeStatus.NEW:
        # Возврат в «новое» стирает и след разбора: иначе запись выглядела бы
        # разобранной кем-то, хотя ждёт работы.
        row.handled_by = None
        row.handled_at = None
    else:
        row.handled_by = str(access.user.id)
        row.handled_at = datetime.now(tz=timezone.utc)
    await session.commit()
    await session.refresh(row)
    return _change_read(row)


@router.get("/{mcid}/readiness", response_model=ClientReadinessRead)
async def get_client_readiness(
    mcid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ClientReadinessRead:
    """Светофор соответствия клиента: факт против эталона (разд. 51.3).

    Отличие от «Центра внимания»: тот показывает ПРОСРОЧКИ существующих
    записей, а эталон — ОТСУТСТВИЕ положенного: сотрудник, которому по норме
    должности положен медосмотр, а записи нет вовсе, во «внимании» не
    появится никогда — там нечему просрочиваться.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    client = await _get(session, tenant, mcid)

    if client.mode is ManagedClientMode.DEDICATED or not client.company_id:
        return ClientReadinessRead(
            client_id=client.id,
            client_name=client.name,
            aggregation="not_aggregated",
            reason=DEDICATED_REASON,
        )

    numbers = await collect_client_numbers(
        session, tenant_id=str(tenant.id), company_id=str(client.company_id)
    )
    # Дисциплины вне редакции исполнителя — вне светофора, но названы (срез-55).
    applicability = await collect_applicability(session, str(tenant.id))
    rows = only_applicable(
        build_directions(
            medical=numbers.medical,
            ppe=numbers.ppe,
            training_overdue=numbers.training_overdue,
            road_safety=numbers.road_safety,
            fire_safety=numbers.fire_safety,
        ),
        applicability,
    )
    return ClientReadinessRead(
        client_id=client.id,
        client_name=client.name,
        aggregation="aggregated",
        overall=worst_light(rows).value,
        not_applicable=applicability.note,
        directions=[
            DirectionReadinessRead(
                direction=row.discipline.value,
                title=row.title,
                light=row.light.value,
                reason=row.reason,
                required=row.counts.required,
                missing=row.counts.missing,
                lapsed=row.counts.lapsed,
                expiring=row.counts.expiring,
            )
            for row in rows
        ],
    )


@router.post("/audit/run", response_model=AuditRunRead)
@audit_operation("create", "client_audit_report")
async def run_client_audit(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> AuditRunRead:
    """Собрать отчёты авто-аудита по всем клиентам сейчас (разд. 51.3).

    Регулярно то же самое делает еженедельный тик
    (``managed_clients.audit.tick``); ручной запуск нужен, чтобы «раз в
    неделю» было проверяемо человеком, а не предметом веры. Повторный запуск
    в тот же день безвреден: отчёт за дату не пишется второй раз.
    """

    TenantContextValidator.ensure_tenant_context(tenant)

    outcome = await run_tenant_audit(session, str(tenant.id))
    await session.commit()
    parts = [f"Создано отчётов: {outcome.created}"]
    if outcome.already_current:
        parts.append(f"уже есть за сегодня: {outcome.already_current}")
    if outcome.skipped_dedicated:
        parts.append(f"пропущено (свой контур): {outcome.skipped_dedicated}")
    return AuditRunRead(
        created=outcome.created,
        already_current=outcome.already_current,
        skipped_dedicated=outcome.skipped_dedicated,
        summary=", ".join(parts),
    )


@router.post("/{mcid}/audit-reports/{report_id}/send", response_model=ReportSendRead)
@audit_operation("update", "client_audit_report")
async def send_client_audit_report(
    mcid: str,
    report_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ReportSendRead:
    """Отправить отчёт аудита клиенту письмом (разд. 51.3, последний пункт).

    Отправка требует ДВУХ условий: адреса и согласия. Знать e-mail и иметь
    право на него писать — разные вещи, и без согласия ручка отказывает
    словами, а не молчит.

    Итог отдаётся причиной, а не голым «не получилось»: «клиент не давал
    согласия» чинит специалист, а «почта не настроена» — администратор.
    """

    TenantContextValidator.ensure_tenant_context(tenant)
    client = await _get(session, tenant, mcid)

    report = (
        await session.execute(
            select(ClientAuditReport).where(
                ClientAuditReport.tenant_id == tenant.id,
                ClientAuditReport.managed_client_id == mcid,
                ClientAuditReport.id == report_id,
            )
        )
    ).scalar_one_or_none()
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")

    outcome = await send_report_to_client(client, report)
    if outcome.status is ReportSendStatus.SENT:
        # Отметка ставится на УСПЕШНУЮ доставку: это и есть подтверждение
        # адреса, после которого автоматическая рассылка становится безопасной.
        client.report_verified_at = datetime.now(tz=timezone.utc)
        await session.flush()
    return ReportSendRead(
        status=outcome.status.value, reason=outcome.reason, recipient=outcome.recipient
    )


@router.get("/{mcid}/audit-reports", response_model=ClientAuditReportPage)
async def list_client_audit_reports(
    mcid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: Annotated[int, Query(ge=1, le=50)] = 12,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientAuditReportPage:
    """Отчёты авто-аудита клиента: свежие сверху (разд. 51.3)."""

    TenantContextValidator.ensure_tenant_context(tenant)
    await _get(session, tenant, mcid)

    where = (
        ClientAuditReport.tenant_id == tenant.id,
        ClientAuditReport.managed_client_id == mcid,
    )
    total = int((await session.execute(select(func.count()).where(*where))).scalar_one() or 0)
    rows = (
        (
            await session.execute(
                select(ClientAuditReport)
                .where(*where)
                .order_by(ClientAuditReport.period_end.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return ClientAuditReportPage(
        items=[
            ClientAuditReportRead(
                id=row.id,
                period_start=row.period_start,
                period_end=row.period_end,
                overall=row.overall,
                summary=row.summary,
                payload=dict(row.payload or {}),
            )
            for row in rows
        ],
        total=total,
    )


def _dq_summary(outcome: DqSignalsOutcome) -> str:
    if outcome.found == 0:
        return "Просрочек не найдено"
    parts = [f"Найдено просрочек: {outcome.found}", f"записано в ленты: {outcome.recorded}"]
    if outcome.already_in_feed:
        parts.append(f"уже в лентах: {outcome.already_in_feed}")
    if outcome.not_client_related:
        parts.append(f"не про клиентов: {outcome.not_client_related}")
    if outcome.unparsed:
        parts.append(f"не разобрано: {outcome.unparsed}")
    if outcome.deferred:
        parts.append(f"отложено до следующего сбора: {outcome.deferred}")
    return ", ".join(parts)


@router.post("/dq-signals", response_model=DqSignalsRead)
@audit_operation("create", "client_change")
async def collect_data_quality_signals(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> DqSignalsRead:
    """Собрать просрочки из проверок качества данных в ленты клиентов (51.2).

    ТЗ называет Data Quality третьим источником сигналов: просрочка — тоже
    «изменение состояния». Проверки просрочки переиспользуются из отчёта
    качества данных, в ленту попадают только находки по обслуживаемым
    клиентам, и только один раз: личность находки включает запись и дату
    истечения, поэтому повторный сбор ленту не удваивает, а продлённая и
    снова просроченная запись даёт новый сигнал.

    Ключ идемпотентности не нужен: повторное нажатие безвредно по построению
    (второй сбор запишет ноль).
    """

    TenantContextValidator.ensure_tenant_context(tenant)

    outcome = await collect_dq_signals(session, str(tenant.id))
    await session.commit()
    return DqSignalsRead(
        found=outcome.found,
        recorded=outcome.recorded,
        already_in_feed=outcome.already_in_feed,
        not_client_related=outcome.not_client_related,
        unparsed=outcome.unparsed,
        deferred=outcome.deferred,
        truncated=outcome.truncated,
        summary=_dq_summary(outcome),
    )


@router.get("/{mcid}", response_model=ManagedClientRead)
async def get_managed_client(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> ManagedClientRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get(session, tenant, mcid)
    return ManagedClientRead.model_validate(row, from_attributes=True)


@router.patch("/{mcid}", response_model=ManagedClientRead)
async def update_managed_client(
    mcid: str,
    payload: ManagedClientUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ManagedClientRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get(session, tenant, mcid)
    fields = payload.model_dump(exclude_unset=True)

    target_status = fields.pop("contract_status", None)
    if target_status is not None and target_status is not row.contract_status:
        try:
            validate_contract_transition(row.contract_status, target_status)
        except ManagedClientTransitionError as exc:
            raise _conflict(exc)

    # Инварианты режима проверяются на ИТОГОВОМ состоянии и ДО записи: правка
    # одного поля не должна оставить строку в противоречивом виде, а отказ не
    # должен требовать rollback (он снёс бы и остальную работу этой сессии).
    prospective = {
        "mode": fields.get("mode", row.mode),
        "company_id": fields.get("company_id", row.company_id),
        "dedicated_tenant_slug": fields.get("dedicated_tenant_slug", row.dedicated_tenant_slug),
    }
    try:
        validate_mode_binding(
            prospective["mode"],
            company_id=prospective["company_id"],
            tenant_slug=prospective["dedicated_tenant_slug"],
        )
    except ManagedClientTransitionError as exc:
        raise _invalid(exc)

    if target_status is not None:
        row.contract_status = target_status

    # BIZ-51 срез-193: смена адреса ОБНУЛЯЕТ подтверждение доставки. Новый
    # адрес — снова непроверенный, и автоматика на него не пишет, пока отчёт не
    # уйдёт туда вручную. Иначе опечатка в правке адреса сразу уехала бы в
    # автоматическую рассылку — ровно то, ради чего автоматику и сдерживали.
    new_email = fields.get("report_email", None)
    if "report_email" in fields and (new_email or "") != (row.report_email or ""):
        row.report_verified_at = None

    for field, value in fields.items():
        setattr(row, field, value)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise _err(
            "MANAGED_CLIENT_DUPLICATE",
            "Клиент с таким названием уже есть в портфеле",
            status.HTTP_409_CONFLICT,
        )
    await session.refresh(row)
    return ManagedClientRead.model_validate(row, from_attributes=True)


@router.delete("/{mcid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_managed_client(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> Response:
    """Мягкое удаление: история ведения клиента остаётся (разд. 49.1)."""

    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get(session, tenant, mcid)
    row.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
