"""Obligation summary endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.obligations import Task, TaskStatus
from app.models.models import Tenant
from app.schemas.obligations import ObligationSummary, ObligationSummaryItem

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
