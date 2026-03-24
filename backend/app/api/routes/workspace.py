from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.finance import Contract, ContractStatus
from app.models.models import (
    ComplianceDeadline,
    OfflineSyncBatch,
    PPEIssue,
    PPEIssueStatus,
    Person,
    Tenant,
    TemplateVersion,
    TemplateVersionStatus,
    TrainingEnrollment,
)
from app.models.obligations import Task, TaskStatus
from app.core.permission_checker import PermissionChecker
from app.core.tenant_validation import TenantContextValidator

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
    readiness_blockers: int = 0


class ReadinessBlocker(BaseModel):
    code: str
    title: str
    severity: str
    count: int
    reason: str
    entity_type: str
    action_hint: str


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
    blockers: list[ReadinessBlocker] = Field(default_factory=list)
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


async def _readiness_blockers(
    *,
    session: AsyncSession,
    tenant: Tenant,
    now: datetime,
) -> list[ReadinessBlocker]:
    blockers: list[ReadinessBlocker] = []

    missing_employee_contacts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(
                    Person.tenant_id == tenant.id,
                    Person.deleted_at.is_(None),
                    or_(Person.email.is_(None), Person.phone.is_(None)),
                )
            )
        ).scalar_one()
        or 0
    )
    if missing_employee_contacts > 0:
        blockers.append(
            ReadinessBlocker(
                code="employees_missing_contacts",
                title="Employee profile gaps",
                severity="high",
                count=missing_employee_contacts,
                reason="Employees missing email or phone break notification and assignment flows",
                entity_type="person",
                action_hint="Complete employee contact fields",
            )
        )

    ready_template_versions = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TemplateVersion)
                .where(
                    TemplateVersion.tenant_id == tenant.id,
                    TemplateVersion.deleted_at.is_(None),
                    TemplateVersion.status.in_(
                        [
                            TemplateVersionStatus.ACTIVE,
                            TemplateVersionStatus.READY,
                            TemplateVersionStatus.LINTED,
                        ]
                    ),
                )
            )
        ).scalar_one()
        or 0
    )
    if ready_template_versions == 0:
        blockers.append(
            ReadinessBlocker(
                code="templates_not_ready",
                title="No ready templates",
                severity="critical",
                count=1,
                reason="Document lifecycle cannot run without ready template versions",
                entity_type="template_version",
                action_hint="Upload/lint/activate at least one template version",
            )
        )

    overdue_training = int(
        (
            await session.execute(
                select(func.count())
                .select_from(TrainingEnrollment)
                .where(
                    TrainingEnrollment.tenant_id == tenant.id,
                    TrainingEnrollment.deleted_at.is_(None),
                    TrainingEnrollment.status.in_(["assigned", "in_progress"]),
                    TrainingEnrollment.due_at.is_not(None),
                    TrainingEnrollment.due_at < now,
                )
            )
        ).scalar_one()
        or 0
    )
    if overdue_training > 0:
        blockers.append(
            ReadinessBlocker(
                code="training_overdue",
                title="Overdue training assignments",
                severity="high",
                count=overdue_training,
                reason="Overdue training blocks readiness and increases compliance risk",
                entity_type="training_enrollment",
                action_hint="Close overdue training enrollments or re-plan deadlines",
            )
        )

    expired_ppe = int(
        (
            await session.execute(
                select(func.count())
                .select_from(PPEIssue)
                .where(
                    PPEIssue.tenant_id == tenant.id,
                    PPEIssue.deleted_at.is_(None),
                    PPEIssue.status == PPEIssueStatus.ISSUED,
                    PPEIssue.expires_at.is_not(None),
                    PPEIssue.expires_at < now,
                )
            )
        ).scalar_one()
        or 0
    )
    if expired_ppe > 0:
        blockers.append(
            ReadinessBlocker(
                code="ppe_expired",
                title="Expired issued PPE",
                severity="high",
                count=expired_ppe,
                reason="Expired issued PPE indicates unresolved replacement obligations",
                entity_type="ppe_issue",
                action_hint="Issue replacement PPE or mark return/loss status",
            )
        )

    expired_active_contracts = int(
        (
            await session.execute(
                select(func.count())
                .select_from(Contract)
                .where(
                    Contract.tenant_id == tenant.id,
                    Contract.deleted_at.is_(None),
                    Contract.status == ContractStatus.ACTIVE,
                    Contract.valid_until.is_not(None),
                    Contract.valid_until < date.today(),
                )
            )
        ).scalar_one()
        or 0
    )
    if expired_active_contracts > 0:
        blockers.append(
            ReadinessBlocker(
                code="contracts_expired",
                title="Expired active contracts",
                severity="critical",
                count=expired_active_contracts,
                reason="Expired active contracts break contractor readiness and package flows",
                entity_type="contract",
                action_hint="Close expired contracts or extend validity",
            )
        )

    return blockers


@router.get("/attention", response_model=WorkspaceAttentionResponse)
async def workspace_attention(
    tenant: TenantDep,
    session: SessionDep,
    access: AccessDep,
    limit: int = Query(30, ge=1, le=100),
) -> WorkspaceAttentionResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

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

    blockers = await _readiness_blockers(session=session, tenant=tenant, now=now)

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
    if blockers:
        recs.append("Resolve readiness blockers before launching dependent scenarios")
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
            readiness_blockers=len(blockers),
        ),
        items=items,
        blockers=blockers,
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
    TenantContextValidator.ensure_tenant_context(tenant)

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

    items: list[TaskInboxItem] = []
    for item in rows:
        due_utc = _as_utc(item.due_at)
        items.append(
            TaskInboxItem(
                id=item.id,
                title=item.title,
                status=item.status.value,
                priority=item.priority.value,
                due_at=item.due_at,
                assignee_id=item.assignee_id,
                entity_type=item.entity_type,
                entity_id=item.entity_id,
                overdue=bool(due_utc and due_utc < now),
            )
        )
    overdue_count = sum(1 for item in items if item.overdue)
    return WorkspaceTaskInboxResponse(total=total, overdue=overdue_count, items=items)
