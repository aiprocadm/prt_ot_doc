from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.finance import Contract, Invoice, InvoiceStatus, Order
from app.models.models import Tenant
from app.schemas.invoice import InvoiceCreate, InvoicePage, InvoiceRead, InvoiceUpdate

router = APIRouter(tags=["invoices"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_INVOICE_READ_ROLES = ["admin", "owner", "accountant"]
_INVOICE_WRITE_ROLES = ["admin", "owner", "accountant"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_INVOICE_READ_ROLES, action="read invoices")),
]

WriteAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_INVOICE_WRITE_ROLES, action="manage invoices")),
]


def _invoice_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(code="INVOICE_VALIDATION_ERROR", message=message, error_type="invoices"),
    )


def _invoice_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(code="INVOICE_VALIDATION_ERROR", message=message, error_type="invoices"),
    )


async def _get_contract(session: AsyncSession, tenant: Tenant, contract_id: str) -> Contract:
    stmt = select(Contract).where(
        Contract.id == contract_id,
        Contract.tenant_id == tenant.id,
        Contract.deleted_at.is_(None),
    )
    contract = (await session.execute(stmt)).scalar_one_or_none()
    if contract is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contract not found")
    return contract


async def _get_order(session: AsyncSession, tenant: Tenant, order_id: str) -> Order:
    stmt = select(Order).where(
        Order.id == order_id,
        Order.tenant_id == tenant.id,
        Order.deleted_at.is_(None),
    )
    order = (await session.execute(stmt)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    return order


async def _get_invoice(session: AsyncSession, tenant: Tenant, invoice_id: str) -> Invoice:
    stmt = select(Invoice).where(
        Invoice.id == invoice_id,
        Invoice.tenant_id == tenant.id,
        Invoice.deleted_at.is_(None),
    )
    invoice = (await session.execute(stmt)).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


@router.get("/invoices", response_model=InvoicePage)
async def list_invoices(
    tenant: TenantDep,
    session: SessionDep,
    _: ReadAccess,
    correlation_id: str = Depends(get_correlation_id),
    contract_id: str | None = Query(default=None, min_length=1, max_length=36),
    order_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InvoicePage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Invoice).where(
        Invoice.tenant_id == tenant.id,
        Invoice.deleted_at.is_(None),
    )
    if contract_id:
        stmt = stmt.where(Invoice.contract_id == contract_id)
    if order_id:
        stmt = stmt.where(Invoice.order_id == order_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Invoice.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return InvoicePage(items=items, total=int(total or 0))


@router.post("/invoices", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "invoice")
async def create_invoice(
    payload: InvoiceCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> InvoiceRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    contract = await _get_contract(session, tenant, payload.contract_id)
    order_id = payload.order_id
    if order_id:
        order = await _get_order(session, tenant, order_id)
        if order.contract_id != contract.id:
            raise _invoice_bad_request("Order does not belong to contract")
    if payload.status:
        try:
            status_value = InvoiceStatus(str(payload.status).lower())
        except ValueError as exc:
            raise _invoice_unprocessable("Unsupported invoice status") from exc
    else:
        status_value = InvoiceStatus.ISSUED
    invoice = Invoice(
        tenant_id=str(tenant.id),
        contract_id=contract.id,
        order_id=payload.order_id,
        invoice_number=payload.invoice_number,
        status=status_value,
        issued_at=payload.issued_at,
        due_at=payload.due_at,
        paid_at=payload.paid_at,
        total_amount=payload.total_amount,
        currency=payload.currency or "RUB",
    )
    session.add(invoice)
    await session.commit()
    await session.refresh(invoice)
    return InvoiceRead.model_validate(invoice)


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ReadAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> InvoiceRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    invoice = await _get_invoice(session, tenant, invoice_id)
    return InvoiceRead.model_validate(invoice)


@router.patch("/invoices/{invoice_id}", response_model=InvoiceRead)
@audit_operation("update", "invoice")
async def update_invoice(
    invoice_id: str,
    payload: InvoiceUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> InvoiceRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    invoice = await _get_invoice(session, tenant, invoice_id)
    updates = payload.model_dump(exclude_unset=True)
    if "contract_id" in updates and updates["contract_id"]:
        contract = await _get_contract(session, tenant, str(updates["contract_id"]))
        invoice.contract_id = contract.id
    if "order_id" in updates and updates["order_id"]:
        order = await _get_order(session, tenant, str(updates["order_id"]))
        if order.contract_id != invoice.contract_id:
            raise _invoice_bad_request("Order does not belong to contract")
        invoice.order_id = order.id
    if "status" in updates and updates["status"]:
        try:
            updates["status"] = InvoiceStatus(str(updates["status"]).lower())
        except ValueError as exc:
            raise _invoice_unprocessable("Unsupported invoice status") from exc
    for key, value in updates.items():
        setattr(invoice, key, value)
    await session.commit()
    await session.refresh(invoice)
    return InvoiceRead.model_validate(invoice)


@router.delete(
    "/invoices/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
@audit_operation("delete", "invoice")
async def delete_invoice(
    invoice_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    invoice = await _get_invoice(session, tenant, invoice_id)
    if invoice.deleted_at is None:
        invoice.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
