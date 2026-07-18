"""Dashboard summary and operational projection endpoints."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.document_core import PipelineRun, PipelineRunStatus, Template
from app.models.models import Incident, IncidentStatus, TrainingPlan
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.models.risk import RiskAssessment
from app.models.safety_ops import InspectionPrepGap, InspectionPrepPackage
from app.models.tenanting import Tenant
from app.schemas.dashboard import (
    DashboardDocumentInboxItem,
    DashboardOperationalSnapshot,
    DashboardReadinessSnapshot,
    DashboardSummary,
    DashboardTaskInboxItem,
    DashboardTrainingSummary,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)

_SUMMARY_ROLES = ["admin", "owner", "line_manager", "hr", "ot_pb_lead"]


def _as_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


SummaryAccess = Depends(
    abac(_tenant_resource_id, required_roles=_SUMMARY_ROLES, action="read dashboard")
)


async def _scalar(session: AsyncSession, stmt) -> int:
    value = await session.scalar(stmt)
    return int(value or 0)


async def _safe_scalar(session: AsyncSession, stmt, default: int = 0) -> int:
    try:
        return await _scalar(session, stmt)
    except OperationalError:
        return default


async def _safe_max_datetime(session: AsyncSession, stmt):
    try:
        return await session.scalar(stmt)
    except OperationalError:
        return None


@router.get("/summary", response_model=DashboardSummary)
async def dashboard_summary(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
) -> DashboardSummary:
    TenantContextValidator.ensure_tenant_context(tenant)

    now = datetime.now(timezone.utc)
    today = date.today()
    due_soon_date = today + timedelta(days=14)
    open_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    overdue_tasks_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant.id,
            Task.status.in_(open_statuses),
            Task.due_at.is_not(None),
            Task.due_at < now,
        )
    )
    critical_obligations_stmt = (
        select(func.count())
        .select_from(Task)
        .where(
            Task.tenant_id == tenant.id,
            Task.status.in_(open_statuses),
            Task.priority.in_([TaskPriority.HIGH, TaskPriority.CRITICAL]),
            Task.due_at.is_not(None),
            Task.due_at <= now + timedelta(days=7),
        )
    )
    incidents_open_stmt = (
        select(func.count())
        .select_from(Incident)
        .where(
            Incident.tenant_id == tenant.id,
            Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.CANCELLED]),
        )
    )
    risks_total_stmt = (
        select(func.count())
        .select_from(RiskAssessment)
        .where(RiskAssessment.tenant_id == tenant.id)
    )
    training_total_stmt = (
        select(func.count()).select_from(TrainingPlan).where(TrainingPlan.tenant_id == tenant.id)
    )
    training_overdue_stmt = (
        select(func.count())
        .select_from(TrainingPlan)
        .where(
            TrainingPlan.tenant_id == tenant.id,
            TrainingPlan.due_date.is_not(None),
            TrainingPlan.due_date < today,
        )
    )
    training_due_soon_stmt = (
        select(func.count())
        .select_from(TrainingPlan)
        .where(
            TrainingPlan.tenant_id == tenant.id,
            TrainingPlan.due_date.is_not(None),
            TrainingPlan.due_date >= today,
            TrainingPlan.due_date <= due_soon_date,
        )
    )

    overdue_tasks = await _scalar(session, overdue_tasks_stmt)
    critical_obligations = await _scalar(session, critical_obligations_stmt)
    incidents_open = await _scalar(session, incidents_open_stmt)
    risks_total = await _scalar(session, risks_total_stmt)
    training_total = await _scalar(session, training_total_stmt)
    training_overdue = await _scalar(session, training_overdue_stmt)
    training_due_soon = await _scalar(session, training_due_soon_stmt)

    if training_overdue > 0:
        training_status = "critical"
    elif training_due_soon > 0:
        training_status = "warning"
    else:
        training_status = "ok"

    return DashboardSummary(
        overdue_tasks=overdue_tasks,
        critical_obligations=critical_obligations,
        incidents_open=incidents_open,
        risks_total=risks_total,
        training=DashboardTrainingSummary(
            total=training_total,
            overdue=training_overdue,
            due_soon=training_due_soon,
            status=training_status,
        ),
        generated_at=now.isoformat(),
    )


def _task_owner_label(task: Task) -> str | None:
    if task.assignee_id:
        return task.assignee_id[:8]
    return "Не назначен"


def _pipeline_route_label(status: PipelineRunStatus) -> str:
    normalized = status.value if hasattr(status, "value") else str(status)
    return {
        "queued": "В очереди",
        "running": "Генерация",
        "done": "Готов",
        "error": "Ошибка",
        "canceled": "Отменен",
    }.get(normalized, normalized)


def _pipeline_risk(status: PipelineRunStatus) -> str:
    normalized = status.value if hasattr(status, "value") else str(status)
    if normalized == "error":
        return "high"
    if normalized in {"queued", "running"}:
        return "medium"
    return "low"


@router.get("/operational", response_model=DashboardOperationalSnapshot)
async def dashboard_operational_snapshot(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = SummaryAccess,
) -> DashboardOperationalSnapshot:
    TenantContextValidator.ensure_tenant_context(tenant)

    now = datetime.now(timezone.utc)
    open_task_statuses = [TaskStatus.OPEN, TaskStatus.IN_PROGRESS]

    task_rows = (
        (
            await session.execute(
                select(Task)
                .where(
                    Task.tenant_id == tenant.id,
                    Task.status.in_(open_task_statuses),
                )
                .order_by(
                    case((Task.due_at.is_(None), 1), else_=0),
                    Task.due_at.asc(),
                    Task.created_at.desc(),
                )
                .limit(5)
            )
        )
        .scalars()
        .all()
    )

    document_rows = (
        await session.execute(
            select(PipelineRun, Template)
            .join(Template, Template.id == PipelineRun.template_id)
            .where(PipelineRun.tenant_id == tenant.id)
            .order_by(PipelineRun.created_at.desc())
            .limit(5)
        )
    ).all()

    packages_total = await _safe_scalar(
        session,
        select(func.count())
        .select_from(InspectionPrepPackage)
        .where(
            InspectionPrepPackage.tenant_id == str(tenant.id),
            InspectionPrepPackage.deleted_at.is_(None),
        ),
    )
    open_gaps = await _safe_scalar(
        session,
        select(func.count())
        .select_from(InspectionPrepGap)
        .where(
            InspectionPrepGap.tenant_id == str(tenant.id),
            InspectionPrepGap.status == "open",
        ),
    )
    critical_gaps = await _safe_scalar(
        session,
        select(func.count())
        .select_from(InspectionPrepGap)
        .where(
            InspectionPrepGap.tenant_id == str(tenant.id),
            InspectionPrepGap.status == "open",
            InspectionPrepGap.severity == "critical",
        ),
    )
    latest_target_date = await _safe_max_datetime(
        session,
        select(func.max(InspectionPrepPackage.target_inspection_date)).where(
            InspectionPrepPackage.tenant_id == str(tenant.id),
            InspectionPrepPackage.deleted_at.is_(None),
        ),
    )

    readiness_score = max(0, 100 - min(70, open_gaps * 10 + critical_gaps * 15))
    reasons: list[str] = []
    if packages_total == 0:
        reasons.append("Нет зарегистрированных inspection-prep пакетов.")
    if open_gaps > 0:
        reasons.append(f"Есть незакрытые gaps: {open_gaps}.")
    if critical_gaps > 0:
        reasons.append(f"Есть критичные blockers: {critical_gaps}.")
    if not reasons:
        reasons.append("Открытых blockers не обнаружено.")

    return DashboardOperationalSnapshot(
        tasks=[
            DashboardTaskInboxItem(
                id=str(task.id),
                title=task.title,
                owner_label=_task_owner_label(task),
                due_at=_as_utc_datetime(task.due_at).isoformat() if task.due_at else None,
                priority=(
                    task.priority.value if hasattr(task.priority, "value") else str(task.priority)
                ),
                status=task.status.value if hasattr(task.status, "value") else str(task.status),
                overdue=bool((due_at := _as_utc_datetime(task.due_at)) and due_at < now),
                entity_type=task.entity_type,
                entity_id=task.entity_id,
            )
            for task in task_rows
        ],
        documents=[
            DashboardDocumentInboxItem(
                id=str(run.id),
                title=template.name,
                route_label=_pipeline_route_label(run.status),
                status=run.status.value if hasattr(run.status, "value") else str(run.status),
                risk=_pipeline_risk(run.status),
                created_at=run.created_at.isoformat(),
                template_code=template.code,
                template_version=None,
            )
            for run, template in document_rows
        ],
        readiness=DashboardReadinessSnapshot(
            packages_total=packages_total,
            open_gaps=open_gaps,
            critical_gaps=critical_gaps,
            latest_target_date=latest_target_date.isoformat() if latest_target_date else None,
            readiness_score=readiness_score,
            reasons=reasons,
        ),
        generated_at=now.isoformat(),
    )
