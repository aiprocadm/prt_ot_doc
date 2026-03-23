from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import ComplianceDeadline, OfflineSyncBatch, Tenant
from app.models.obligations import Task, TaskStatus

router = APIRouter(prefix="/workspace", tags=["workspace"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]


class AttentionSummary(BaseModel):
    overdue_tasks: int = 0
    due_soon_tasks: int = 0
    overdue_deadlines: int = 0
    pending_sync_batches: int = 0
    failed_sync_batches: int = 0


class AttentionItem(BaseModel):
    item_type: str
    id: str
    severity: str
    title: str
    status: str
    due_at: datetime | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    reason: str


class WorkspaceAttentionResponse(BaseModel):
    generated_at: datetime
    summary: AttentionSummary
    items: list[AttentionItem] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class TaskInboxItem(BaseModel):
    id: str
    title: str
    status: str
    priority: str
    due_at: datetime | None = None
    assignee_id: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    overdue: bool = False


class WorkspaceTaskInboxResponse(BaseModel):
    total: int
    overdue: int
    items: list[TaskInboxItem] = Field(default_factory=list)


def _worker_like_role(role: str) -> bool:
    return role in {"worker", "client_user"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@router.get("/attention", response_model=WorkspaceAttentionResponse)
async def workspace_attention(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
    limit: int = Query(30, ge=1, le=100),
) -> WorkspaceAttentionResponse:
    now = datetime.now(timezone.utc)
    soon_threshold = now + timedelta(days=3)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    task_stmt = select(Task).where(
        Task.tenant_id == tenant.id,
        Task.status.in_(open_statuses),
    )
    if _worker_like_role(access.user.role.value):
        task_stmt = task_stmt.where(Task.assignee_id == access.user.id)

    overdue_task_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == tenant.id,
                    Task.status.in_(open_statuses),
                    Task.due_at.is_not(None),
                    Task.due_at < now,
                    Task.assignee_id == access.user.id if _worker_like_role(access.user.role.value) else True,
                )
            )
        ).scalar_one()
        or 0
    )
    due_soon_task_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == tenant.id,
                    Task.status.in_(open_statuses),
                    Task.due_at.is_not(None),
                    Task.due_at >= now,
                    Task.due_at <= soon_threshold,
                    Task.assignee_id == access.user.id if _worker_like_role(access.user.role.value) else True,
                )
            )
        ).scalar_one()
        or 0
    )

    overdue_deadline_total = int(
        (
            await session.execute(
                select(func.count())
                .select_from(ComplianceDeadline)
                .where(
                    ComplianceDeadline.tenant_id == tenant.id,
                    or_(ComplianceDeadline.status == "overdue", and_(ComplianceDeadline.status == "due", ComplianceDeadline.due_at < now)),
                )
            )
        ).scalar_one()
        or 0
    )

    pending_sync = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OfflineSyncBatch)
                .where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "pending",
                )
            )
        ).scalar_one()
        or 0
    )
    failed_sync = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OfflineSyncBatch)
                .where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "failed",
                )
            )
        ).scalar_one()
        or 0
    )

    candidate_tasks = (
        await session.execute(
            task_stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc()).limit(limit)
        )
    ).scalars().all()

    items: list[AttentionItem] = []
    for task in candidate_tasks:
        due_at = task.due_at.astimezone(timezone.utc) if task.due_at else None
        if due_at and due_at < now:
            severity = "critical"
            reason = "Task is overdue"
        elif due_at and due_at <= soon_threshold:
            severity = "high"
            reason = "Task is due soon"
        else:
            severity = "medium"
            reason = "Open task"
        items.append(
            AttentionItem(
                item_type="task",
                id=task.id,
                severity=severity,
                title=task.title,
                status=task.status.value,
                due_at=task.due_at,
                entity_type=task.entity_type,
                entity_id=task.entity_id,
                reason=reason,
            )
        )

    recs: list[str] = []
    if overdue_task_total > 0:
        recs.append("Resolve overdue tasks first")
    if overdue_deadline_total > 0:
        recs.append("Address overdue compliance deadlines")
    if failed_sync > 0:
        recs.append("Review failed offline sync batches before next field upload")
    if not recs:
        recs.append("No critical blockers detected. Continue planned work queue")

    return WorkspaceAttentionResponse(
        generated_at=now,
        summary=AttentionSummary(
            overdue_tasks=overdue_task_total,
            due_soon_tasks=due_soon_task_total,
            overdue_deadlines=overdue_deadline_total,
            pending_sync_batches=pending_sync,
            failed_sync_batches=failed_sync,
        ),
        items=items,
        recommendations=recs,
    )


@router.get("/task-inbox", response_model=WorkspaceTaskInboxResponse)
async def workspace_task_inbox(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WorkspaceTaskInboxResponse:
    now = datetime.now(timezone.utc)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]
    stmt = select(Task).where(Task.tenant_id == tenant.id, Task.status.in_(open_statuses))
    if _worker_like_role(access.user.role.value):
        stmt = stmt.where(Task.assignee_id == access.user.id)

    total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0)
    rows = (
        await session.execute(
            stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    items = [
        TaskInboxItem(
            id=item.id,
            title=item.title,
            status=item.status.value,
            priority=item.priority.value,
            due_at=item.due_at,
            assignee_id=item.assignee_id,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            overdue=bool(_as_utc(item.due_at) and _as_utc(item.due_at) < now),
        )
        for item in rows
    ]
    overdue_count = sum(1 for item in items if item.overdue)
    return WorkspaceTaskInboxResponse(total=total, overdue=overdue_count, items=items)
