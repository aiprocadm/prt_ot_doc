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
from app.models.finance import Contract, Order, OrderStatus
from app.models.models import Tenant
from app.schemas.order import OrderCreate, OrderPage, OrderRead, OrderUpdate

router = APIRouter(tags=["orders"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_ORDER_READ_ROLES = ["admin", "owner", "accountant"]
_ORDER_WRITE_ROLES = ["admin", "owner", "accountant"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ORDER_READ_ROLES, action="read orders")),
]

WriteAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ORDER_WRITE_ROLES, action="manage orders")),
]


def _order_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(code="ORDER_VALIDATION_ERROR", message=message, error_type="orders"),
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


@router.get("/orders", response_model=OrderPage)
async def list_orders(
    tenant: TenantDep,
    session: SessionDep,
    _: ReadAccess,
    correlation_id: str = Depends(get_correlation_id),
    contract_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> OrderPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Order).where(
        Order.tenant_id == tenant.id,
        Order.deleted_at.is_(None),
    )
    if contract_id:
        stmt = stmt.where(Order.contract_id == contract_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    return OrderPage(items=items, total=int(total or 0))


@router.post("/orders", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "order")
async def create_order(
    payload: OrderCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> OrderRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    contract = await _get_contract(session, tenant, payload.contract_id)
    if payload.status:
        try:
            status_value = OrderStatus(str(payload.status).lower())
        except ValueError as exc:
            raise _order_unprocessable("Unsupported order status") from exc
    else:
        status_value = OrderStatus.DRAFT
    order = Order(
        tenant_id=str(tenant.id),
        contract_id=contract.id,
        order_number=payload.order_number,
        status=status_value,
        ordered_at=payload.ordered_at,
        total_amount=payload.total_amount,
        currency=payload.currency or "RUB",
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return OrderRead.model_validate(order)


@router.get("/orders/{order_id}", response_model=OrderRead)
async def get_order(
    order_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ReadAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> OrderRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    order = await _get_order(session, tenant, order_id)
    return OrderRead.model_validate(order)


@router.patch("/orders/{order_id}", response_model=OrderRead)
@audit_operation("update", "order")
async def update_order(
    order_id: str,
    payload: OrderUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> OrderRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    order = await _get_order(session, tenant, order_id)
    updates = payload.model_dump(exclude_unset=True)
    if "contract_id" in updates and updates["contract_id"]:
        contract = await _get_contract(session, tenant, str(updates["contract_id"]))
        order.contract_id = contract.id
    if "status" in updates and updates["status"]:
        try:
            updates["status"] = OrderStatus(str(updates["status"]).lower())
        except ValueError as exc:
            raise _order_unprocessable("Unsupported order status") from exc
    for key, value in updates.items():
        setattr(order, key, value)
    await session.commit()
    await session.refresh(order)
    return OrderRead.model_validate(order)


@router.delete(
    "/orders/{order_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
@audit_operation("delete", "order")
async def delete_order(
    order_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: WriteAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    order = await _get_order(session, tenant, order_id)
    if order.deleted_at is None:
        order.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
