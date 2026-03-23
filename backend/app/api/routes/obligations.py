"""Obligation summary endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.models.obligations import Task, TaskStatus
from app.models.models import Tenant
from app.schemas.obligations import ObligationSummary, ObligationSummaryItem
from app.schemas.task import TaskRead

router = APIRouter(tags=["obligations"])

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)

_SUMMARY_ROLES = ["admin", "owner", "line_manager", "hr"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


SummaryAccess = Depends(
    abac(_tenant_resource_id, required_roles=_SUMMARY_ROLES, action="read obligations")
)


@router.get("/obligations/summary", response_model=ObligationSummary)
async def obligations_summary(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
) -> ObligationSummary:
    now = datetime.now(timezone.utc)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]
    overdue_case = case(
        (
            Task.due_at.is_not(None)
            & (Task.due_at < now)
            & Task.status.in_(open_statuses),
            1,
        ),
        else_=0,
    )
    stmt = (
        select(
            Task.entity_type,
            func.count().label("total"),
            func.coalesce(func.sum(overdue_case), 0).label("overdue"),
        )
        .where(Task.tenant_id == tenant.id, Task.status.in_(open_statuses))
        .group_by(Task.entity_type)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        ObligationSummaryItem(
            entity_type=row.entity_type,
            total=int(row.total or 0),
            overdue=int(row.overdue or 0),
        )
        for row in rows
    ]
    total = sum(item.total for item in items)
    overdue = sum(item.overdue for item in items)
    return ObligationSummary(items=items, total=total, overdue=overdue)


@router.get("/obligations", response_model=list[TaskRead])
async def list_obligations(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
    overdue: bool = Query(default=False),
    site_id: str | None = Query(default=None),
) -> list[TaskRead]:
    now = datetime.now(timezone.utc)
    stmt = select(Task).where(Task.tenant_id == tenant.id)
    if overdue:
        stmt = stmt.where(
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
    if site_id:
        stmt = stmt.where(Task.description.ilike(f"%{site_id}%"))
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [TaskRead.model_validate(row) for row in rows]


@router.patch("/obligations/{obligation_id}", response_model=TaskRead)
@audit_operation("close", "obligation")
async def close_obligation(
    obligation_id: str,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
) -> TaskRead:
    task = await session.get(Task, obligation_id)
    if task is None or task.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Obligation not found")
    task.status = TaskStatus.DONE
    task.completed_at = datetime.now(timezone.utc)
    await session.flush()
    await session.refresh(task)
    return TaskRead.model_validate(task)
