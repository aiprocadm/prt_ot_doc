"""Budget API (§12.4 срез-1): бюджеты доменов / статьи / журнал расходов / сводка.

За фичефлагом ``budget`` (default-off → 404, паттерн rules_engine/api.py).
RBAC: admin/owner/accountant/ot_pb_lead — единый Access на чтение и запись.
Факт нигде не персистится: detail/overview/breakdown считают его на лету
через app.modules.budget.aggregation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
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
from app.models.budget import BudgetExpense, BudgetExpenseArticle
from app.models.models import Tenant
from app.modules.budget.aggregation import (
    compute_breakdown,
    compute_domain_actual,
    compute_overview,
)
from app.modules.budget.service import (
    ArticleCodeConflict,
    ArticleNotFound,
    BudgetNotFound,
    BudgetService,
    BudgetValidationError,
    ExpenseNotFound,
)
from app.schemas.budget import (
    BudgetArticleActualRead,
    BudgetArticleCreate,
    BudgetArticlePage,
    BudgetArticleRead,
    BudgetArticleUpdate,
    BudgetBreakdownResponse,
    BudgetExpenseCreate,
    BudgetExpensePage,
    BudgetExpenseRead,
    BudgetExpenseUpdate,
    BudgetOverviewResponse,
    BudgetSeedResult,
    SafetyBudgetCreate,
    SafetyBudgetDetail,
    SafetyBudgetPage,
    SafetyBudgetRead,
    SafetyBudgetUpdate,
)
from app.services.audit import AuditService

router = APIRouter(prefix="/budget", tags=["budget"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ROLES = ["admin", "owner", "accountant", "ot_pb_lead"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


Access = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ROLES, action="manage safety budget")),
]

_FEATURE_CODE = "budget"


async def _require_feature(
    session: SessionDep,
    tenant: TenantDep,
) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="BUDGET_DISABLED",
                message="Budget feature is not enabled for this tenant",
                error_type="budget",
            ),
        )


FeatureGate = Depends(_require_feature)


def _error(code: str, message: str) -> dict:
    return api_problem_detail(code=code, message=message, error_type="budget")


def _budget_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail=_error("BUDGET_NOT_FOUND", "Safety budget not found")
    )


def _article_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=_error("ARTICLE_NOT_FOUND", "Budget expense article not found"),
    )


def _expense_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND, detail=_error("EXPENSE_NOT_FOUND", "Budget expense not found")
    )


def _validation_error(exc: BudgetValidationError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=_error(exc.code, exc.message or exc.code),
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
    object_type: str,
    object_id: str,
    details: dict | None = None,
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _window_defaults(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """Default each missing bound independently to the current calendar year."""
    today = datetime.now(timezone.utc).date()
    if date_from is None:
        date_from = date(today.year, 1, 1)
    if date_to is None:
        date_to = date(today.year, 12, 31)
    return date_from, date_to


async def _resolve_article_name(
    session: AsyncSession, tenant_id: str, article_id: str | None
) -> str | None:
    """Tenant-scoped article name for a single expense response.

    Как и list_expenses — БЕЗ deleted_at-фильтра: расход по soft-deleted статье
    продолжает показывать её историческое имя.
    """
    if article_id is None:
        return None
    return await session.scalar(
        select(BudgetExpenseArticle.name).where(
            BudgetExpenseArticle.tenant_id == tenant_id,
            BudgetExpenseArticle.id == article_id,
        )
    )


def _expense_read(expense: BudgetExpense, article_name: str | None) -> BudgetExpenseRead:
    return BudgetExpenseRead(
        id=expense.id,
        domain=expense.domain,
        article_id=expense.article_id,
        article_name=article_name,
        title=expense.title,
        occurred_on=expense.occurred_on,
        amount=float(expense.amount),
        company_id=expense.company_id,
        branch_id=expense.branch_id,
        site_id=expense.site_id,
        entity_type=expense.entity_type,
        entity_id=expense.entity_id,
        notes=expense.notes,
    )


# ВАЖНО: статические пути объявлены ДО /budgets/{budget_id} — порядок групп:
# /overview, /breakdown, /articles*, /expenses*, /budgets, /budgets/{budget_id}.


@router.get("/overview", response_model=BudgetOverviewResponse, dependencies=[FeatureGate])
async def budget_overview(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> BudgetOverviewResponse:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    date_from, date_to = _window_defaults(date_from, date_to)
    try:
        return await compute_overview(session, str(tenant.id), date_from, date_to)
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc


@router.get("/breakdown", response_model=BudgetBreakdownResponse, dependencies=[FeatureGate])
async def budget_breakdown(
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    dimension: str = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> BudgetBreakdownResponse:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    date_from, date_to = _window_defaults(date_from, date_to)
    try:
        return await compute_breakdown(session, str(tenant.id), dimension, date_from, date_to)
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc


@router.post(
    "/articles",
    response_model=BudgetArticleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_article(
    request: Request,
    payload: BudgetArticleCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> BudgetArticleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = BudgetService(session, str(tenant.id))
    try:
        record = await service.create_article(payload)
    except ArticleCodeConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("ARTICLE_CODE_EXISTS", f"Article code already exists: {payload.code}"),
        ) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="create",
        object_type="budget_expense_article",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    return BudgetArticleRead.model_validate(record)


@router.get("/articles", response_model=BudgetArticlePage, dependencies=[FeatureGate])
async def list_articles(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await BudgetService(session, str(tenant.id)).list_articles(
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
    return BudgetArticlePage(
        items=[BudgetArticleRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/articles/seed-defaults", response_model=BudgetSeedResult, dependencies=[FeatureGate])
async def seed_default_articles(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> BudgetSeedResult:
    TenantContextValidator.ensure_tenant_context(tenant)
    created, skipped = await BudgetService(session, str(tenant.id)).seed_default_articles()
    if created > 0:  # no-op повторный сид не пишет audit-строку
        await _audit(
            session,
            request,
            access,
            str(tenant.id),
            action="seed",
            object_type="budget_expense_article",
            object_id="defaults",
            details={"created": created, "skipped": skipped},
        )
    await session.commit()
    return BudgetSeedResult(created=created, skipped=skipped)


@router.patch(
    "/articles/{article_id}", response_model=BudgetArticleRead, dependencies=[FeatureGate]
)
async def update_article(
    request: Request,
    article_id: str,
    payload: BudgetArticleUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> BudgetArticleRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        record = await BudgetService(session, str(tenant.id)).update_article(article_id, payload)
    except ArticleNotFound as exc:
        raise _article_not_found() from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="update",
        object_type="budget_expense_article",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    return BudgetArticleRead.model_validate(record)


@router.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_article(
    request: Request,
    article_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await BudgetService(session, str(tenant.id)).delete_article(article_id)
    except ArticleNotFound as exc:
        raise _article_not_found() from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="delete",
        object_type="budget_expense_article",
        object_id=article_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/expenses",
    response_model=BudgetExpenseRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_expense(
    request: Request,
    payload: BudgetExpenseCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> BudgetExpenseRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        record = await BudgetService(session, str(tenant.id)).create_expense(payload)
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="create",
        object_type="budget_expense",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    article_name = await _resolve_article_name(session, str(tenant.id), record.article_id)
    return _expense_read(record, article_name)


@router.get("/expenses", response_model=BudgetExpensePage, dependencies=[FeatureGate])
async def list_expenses(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    domain: str | None = Query(None),
    article_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    company_id: str | None = Query(None),
    branch_id: str | None = Query(None),
    site_id: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await BudgetService(session, str(tenant.id)).list_expenses(
        domain=domain,
        article_id=article_id,
        date_from=date_from,
        date_to=date_to,
        company_id=company_id,
        branch_id=branch_id,
        site_id=site_id,
        limit=limit,
        offset=offset,
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[expense for expense, _name in rows],
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("domain", domain or ""),
            ("article_id", article_id or ""),
            ("date_from", str(date_from) if date_from else ""),
            ("date_to", str(date_to) if date_to else ""),
            ("company_id", company_id or ""),
            ("branch_id", branch_id or ""),
            ("site_id", site_id or ""),
            # Joined article names участвуют в теле ответа, но не в (id, updated_at)
            # строк расходов — без этого скаляра rename статьи отдавал бы 304 со
            # старым именем.
            ("article_names", "|".join((name or "") for _, name in rows)),
        ],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return BudgetExpensePage(
        items=[_expense_read(expense, article_name) for expense, article_name in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/expenses/{expense_id}", response_model=BudgetExpenseRead, dependencies=[FeatureGate]
)
async def update_expense(
    request: Request,
    expense_id: str,
    payload: BudgetExpenseUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> BudgetExpenseRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        record = await BudgetService(session, str(tenant.id)).update_expense(expense_id, payload)
    except ExpenseNotFound as exc:
        raise _expense_not_found() from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="update",
        object_type="budget_expense",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    article_name = await _resolve_article_name(session, str(tenant.id), record.article_id)
    return _expense_read(record, article_name)


@router.delete(
    "/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_expense(
    request: Request,
    expense_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await BudgetService(session, str(tenant.id)).delete_expense(expense_id)
    except ExpenseNotFound as exc:
        raise _expense_not_found() from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="delete",
        object_type="budget_expense",
        object_id=expense_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/budgets",
    response_model=SafetyBudgetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_budget(
    request: Request,
    payload: SafetyBudgetCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> SafetyBudgetRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await BudgetService(session, str(tenant.id)).create_budget(payload)
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="create",
        object_type="safety_budget",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    return SafetyBudgetRead.model_validate(record)


@router.get("/budgets", response_model=SafetyBudgetPage, dependencies=[FeatureGate])
async def list_budgets(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    domain: str | None = Query(None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await BudgetService(session, str(tenant.id)).list_budgets(
        domain=domain, limit=limit, offset=offset
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("domain", domain or ""),
        ],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return SafetyBudgetPage(
        items=[SafetyBudgetRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/budgets/{budget_id}", response_model=SafetyBudgetDetail, dependencies=[FeatureGate])
async def get_budget(
    budget_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> SafetyBudgetDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        budget = await BudgetService(session, str(tenant.id)).get_budget(budget_id)
    except BudgetNotFound as exc:
        raise _budget_not_found() from exc
    actual = await compute_domain_actual(
        session, str(tenant.id), budget.domain, budget.period_start, budget.period_end
    )
    # Decimal-safe remaining: planned (Numeric->Decimal) минус факт (float из
    # датакласса) — оба через Decimal(str(...)), float только на границе схемы.
    planned = Decimal(str(budget.planned_amount))
    remaining = float(planned - Decimal(str(actual.actual_total)))
    return SafetyBudgetDetail(
        id=budget.id,
        name=budget.name,
        domain=budget.domain,
        period_start=budget.period_start,
        period_end=budget.period_end,
        planned_amount=float(planned),
        notes=budget.notes,
        actual_total=actual.actual_total,
        remaining=remaining,
        expense_count=actual.expense_count,
        by_article=[
            BudgetArticleActualRead(
                article_id=row.article_id, article_name=row.article_name, amount=row.amount
            )
            for row in actual.by_article
        ],
    )


@router.patch("/budgets/{budget_id}", response_model=SafetyBudgetRead, dependencies=[FeatureGate])
async def update_budget(
    request: Request,
    budget_id: str,
    payload: SafetyBudgetUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> SafetyBudgetRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        record = await BudgetService(session, str(tenant.id)).update_budget(budget_id, payload)
    except BudgetNotFound as exc:
        raise _budget_not_found() from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="update",
        object_type="safety_budget",
        object_id=record.id,
    )
    await session.commit()
    await session.refresh(record)
    return SafetyBudgetRead.model_validate(record)


@router.delete(
    "/budgets/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_budget(
    request: Request,
    budget_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await BudgetService(session, str(tenant.id)).delete_budget(budget_id)
    except BudgetNotFound as exc:
        raise _budget_not_found() from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="delete",
        object_type="safety_budget",
        object_id=budget_id,
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
