"""Reimbursement API (§12.4 срез-2): заявки на возмещение СФР + их состав.

Тот же префикс/флаг/RBAC, что и у ядра бюджета (api.py): фичефлаг ``budget``
(default-off → 404), роли admin/owner/accountant/ot_pb_lead, единый Access на
чтение и запись. Смена статуса — только через POST /{id}/{action} (FSM в
reimbursement_lifecycle.py); PATCH статус не трогает.
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
from app.core.feature_flags import is_module_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.models.budget import BudgetReimbursement
from app.models.models import Tenant
from app.modules.budget.reimbursement_lifecycle import ReimbursementTransitionError
from app.modules.budget.reimbursement_service import (
    ExpenseAlreadyLinked,
    ReimbursementNotFound,
    ReimbursementService,
)
from app.modules.budget.service import BudgetValidationError
from app.schemas.budget import (
    ReimbursementCreate,
    ReimbursementDecision,
    ReimbursementDetail,
    ReimbursementItemCreate,
    ReimbursementItemRead,
    ReimbursementPage,
    ReimbursementRead,
    ReimbursementUpdate,
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
    enabled = await is_module_enabled(session, str(tenant.id), _FEATURE_CODE)
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


def _claim_not_found() -> HTTPException:
    return HTTPException(
        status.HTTP_404_NOT_FOUND,
        detail=_error("REIMBURSEMENT_NOT_FOUND", "Budget reimbursement not found"),
    )


def _validation_error(exc: BudgetValidationError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=_error(exc.code, exc.message or exc.code),
    )


def _transition_conflict(exc: ReimbursementTransitionError) -> HTTPException:
    """Недопустимый переход/правка вне черновика → 409 (конвенция work_permits)."""
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail=_error(
            "REIMBURSEMENT_TRANSITION_INVALID",
            f"invalid transition: {exc.current} -> {exc.target}",
        ),
    )


def _already_linked(exc: ExpenseAlreadyLinked) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        detail=_error(
            "REIMBURSEMENT_EXPENSE_LINKED",
            f"expense already linked: {exc.expense_id}",
        ),
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
        object_type="budget_reimbursement",
        object_id=object_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _claim_read(claim: BudgetReimbursement, item_count: int, items_amount: float):
    return {
        "id": claim.id,
        "title": claim.title,
        "status": claim.status,
        "period_start": claim.period_start,
        "period_end": claim.period_end,
        "requested_amount": float(claim.requested_amount),
        "approved_amount": (
            float(claim.approved_amount) if claim.approved_amount is not None else None
        ),
        "reference": claim.reference,
        "company_id": claim.company_id,
        "decision_reason": claim.decision_reason,
        "submitted_at": claim.submitted_at,
        "decided_at": claim.decided_at,
        "paid_at": claim.paid_at,
        "notes": claim.notes,
        "item_count": item_count,
        "items_amount": items_amount,
    }


async def _read_one(service: ReimbursementService, claim: BudgetReimbursement) -> ReimbursementRead:
    counts = await service.aggregate_items([claim.id])
    item_count, items_amount = counts.get(claim.id, (0, 0.0))
    return ReimbursementRead(**_claim_read(claim, item_count, items_amount))


# ВАЖНО: /reimbursements/{id}/items объявлен ДО /reimbursements/{id}/{action} —
# иначе POST .../items ушёл бы в FSM-роут с action="items".


@router.post(
    "/reimbursements",
    response_model=ReimbursementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_reimbursement(
    request: Request,
    payload: ReimbursementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ReimbursementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReimbursementService(session, str(tenant.id))
    try:
        record = await service.create_claim(payload)
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(session, request, access, str(tenant.id), action="create", object_id=record.id)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return await _read_one(service, record)


@router.get("/reimbursements", response_model=ReimbursementPage, dependencies=[FeatureGate])
async def list_reimbursements(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    claim_status: str | None = Query(None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    service = ReimbursementService(session, str(tenant.id))
    try:
        rows, total = await service.list_claims(status=claim_status, limit=limit, offset=offset)
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    counts = await service.aggregate_items([row.id for row in rows])
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("status", claim_status or ""),
            # Состав и суммы расходов не входят в (id, updated_at) самой заявки —
            # без этого скаляра привязка расхода отдавала бы 304 со старым составом.
            (
                "items",
                "|".join(
                    f"{row.id}:{counts.get(row.id, (0, 0.0))[0]}:{counts.get(row.id, (0, 0.0))[1]}"
                    for row in rows
                ),
            ),
        ],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return ReimbursementPage(
        items=[
            ReimbursementRead(**_claim_read(row, *counts.get(row.id, (0, 0.0)))) for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/reimbursements/{reimbursement_id}",
    response_model=ReimbursementDetail,
    dependencies=[FeatureGate],
)
async def get_reimbursement(
    reimbursement_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ReimbursementDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    service = ReimbursementService(session, str(tenant.id))
    try:
        claim = await service.get_claim(reimbursement_id)
        expenses = await service.list_items(reimbursement_id)
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    items = [
        ReimbursementItemRead(
            expense_id=expense.id,
            title=expense.title,
            domain=expense.domain,
            occurred_on=expense.occurred_on,
            amount=float(expense.amount),
        )
        for expense in expenses
    ]
    items_amount = float(sum(item.amount for item in items))
    return ReimbursementDetail(
        **_claim_read(claim, len(items), items_amount),
        items=items,
    )


@router.patch(
    "/reimbursements/{reimbursement_id}",
    response_model=ReimbursementRead,
    dependencies=[FeatureGate],
)
async def update_reimbursement(
    request: Request,
    reimbursement_id: str,
    payload: ReimbursementUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ReimbursementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReimbursementService(session, str(tenant.id))
    try:
        record = await service.update_claim(reimbursement_id, payload)
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    except ReimbursementTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(session, request, access, str(tenant.id), action="update", object_id=record.id)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return await _read_one(service, record)


@router.delete(
    "/reimbursements/{reimbursement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_reimbursement(
    request: Request,
    reimbursement_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await ReimbursementService(session, str(tenant.id)).delete_claim(reimbursement_id)
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    except ReimbursementTransitionError as exc:
        raise _transition_conflict(exc) from exc
    await _audit(
        session, request, access, str(tenant.id), action="delete", object_id=reimbursement_id
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reimbursements/{reimbursement_id}/items",
    response_model=ReimbursementItemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def add_reimbursement_item(
    request: Request,
    reimbursement_id: str,
    payload: ReimbursementItemCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> ReimbursementItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    expense_id = payload.expense_id
    try:
        expense = await ReimbursementService(session, str(tenant.id)).add_item(
            reimbursement_id, expense_id
        )
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    except ReimbursementTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except ExpenseAlreadyLinked as exc:
        raise _already_linked(exc) from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="link_expense",
        object_id=reimbursement_id,
        details={"expense_id": expense_id},
    )
    await session.commit()
    return ReimbursementItemRead(
        expense_id=expense.id,
        title=expense.title,
        domain=expense.domain,
        occurred_on=expense.occurred_on,
        amount=float(expense.amount),
    )


@router.delete(
    "/reimbursements/{reimbursement_id}/items/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def remove_reimbursement_item(
    request: Request,
    reimbursement_id: str,
    expense_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await ReimbursementService(session, str(tenant.id)).remove_item(
            reimbursement_id, expense_id
        )
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    except ReimbursementTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="unlink_expense",
        object_id=reimbursement_id,
        details={"expense_id": expense_id},
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/reimbursements/{reimbursement_id}/{action}",
    response_model=ReimbursementRead,
    dependencies=[FeatureGate],
)
async def run_reimbursement_action(
    request: Request,
    reimbursement_id: str,
    action: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    payload: ReimbursementDecision | None = None,
) -> ReimbursementRead:
    """FSM-переход: submit | approve | reject | pay."""
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReimbursementService(session, str(tenant.id))
    try:
        record = await service.run_action(
            reimbursement_id, action, payload or ReimbursementDecision()
        )
    except ReimbursementNotFound as exc:
        raise _claim_not_found() from exc
    except ReimbursementTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except BudgetValidationError as exc:
        raise _validation_error(exc) from exc
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action=f"reimbursement_{action}",
        object_id=record.id,
        details={"status": record.status},
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return await _read_one(service, record)
