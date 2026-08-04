"""Endpoints ведения клиентов аутсорсером (BIZ-49 срез-1, разд. 49.1–49.2).

Портфель — не «просто список»: разд. 49.2 требует видеть по всем клиентам сразу
статус договора, режим ведения и ближайшие сроки. Сводка считается ПО ВСЕМУ
портфелю, а не по странице: «активных 3» на второй странице из пяти — ложь,
за которой руководитель проектов принимает решения.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated

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
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.managed_clients.attention import AggregationStatus, Severity
from app.domains.managed_clients.attention_service import collect_portfolio_attention
from app.domains.managed_clients.calendar import CalendarFilters, DeadlineKind, group_by_date
from app.domains.managed_clients.calendar_service import collect_portfolio_deadlines
from app.domains.managed_clients.lifecycle import (
    ContractStatus,
    ManagedClientMode,
    ManagedClientTransitionError,
    contract_days_left,
    is_contract_expiring,
    validate_contract_transition,
    validate_mode_binding,
)
from app.domains.managed_clients.workload import DEFAULT_THRESHOLDS, OVERLOAD_REASON_TEXT
from app.domains.managed_clients.workload_service import collect_specialist_workload
from app.models.managed_clients import ManagedClient
from app.models.tenanting import Tenant
from app.schemas.managed_clients import (
    AttentionSignalRead,
    CalendarSummary,
    ClientAttentionRead,
    CrossClientAttentionResponse,
    CrossClientAttentionSummary,
    CrossClientCalendarResponse,
    DeadlineDayRead,
    DeadlineEventRead,
    ManagedClientCreate,
    ManagedClientRead,
    ManagedClientUpdate,
    OverloadReasonRead,
    PortfolioItem,
    PortfolioPage,
    PortfolioSummary,
    SpecialistWorkloadRead,
    SpecialistWorkloadResponse,
    WorkloadSummary,
    WorkloadThresholdsRead,
)

router = APIRouter(prefix="/managed-clients", tags=["managed-clients"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Портфель ведёт руководитель проектов аутсорсера; линейным ролям он не нужен
# и показывал бы им коммерческие данные чужих клиентов.
_ROLES = ["admin", "owner", "manager", "ot_pb_lead"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]

_FEATURE_CODE = "managed_clients"

#: Горизонт сигнала «договор истекает» в портфеле.
CONTRACT_EXPIRY_HORIZON_DAYS = 30


def _today() -> date:
    return datetime.now(tz=timezone.utc).date()


async def _require_enabled(session: AsyncSession, tenant: Tenant) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="MANAGED_CLIENTS_DISABLED",
                message="Managed clients module is not enabled for this tenant",
                error_type="managed_clients",
            ),
        )


def _err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=code, message=message, error_type="managed_clients"),
    )


def _invalid(exc: ManagedClientTransitionError) -> HTTPException:
    return _err("MANAGED_CLIENT_MODE_INVALID", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)


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
    await _require_enabled(session, tenant)
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
    await _require_enabled(session, tenant)
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
    await _require_enabled(session, tenant)
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
    await _require_enabled(session, tenant)
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


@router.post("", response_model=ManagedClientRead, status_code=status.HTTP_201_CREATED)
async def create_managed_client(
    payload: ManagedClientCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> ManagedClientRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_enabled(session, tenant)
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


@router.get("/{mcid}", response_model=ManagedClientRead)
async def get_managed_client(
    mcid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> ManagedClientRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_enabled(session, tenant)
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
    await _require_enabled(session, tenant)
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
    await _require_enabled(session, tenant)
    row = await _get(session, tenant, mcid)
    row.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
