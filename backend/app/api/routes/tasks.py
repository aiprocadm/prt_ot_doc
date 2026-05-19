"""Task endpoints for pipeline status and obligations."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import compute_list_etag
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import PipelineRun, Tenant
from app.models.obligations import Task, TaskPriority, TaskStatus
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskPagination,
    TaskRead,
    TaskStatusResponse,
    TaskUpdate,
)
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.obligations import next_task_reminder

router = APIRouter()

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


TaskAccess = Depends(
    abac(_tenant_resource_id, required_roles=["admin"], action="inspect tasks")
)

_TASK_READ_ROLES = ["admin", "owner", "line_manager", "hr", "worker"]
_TASK_WRITE_ROLES = ["admin", "owner", "line_manager", "hr"]


TaskReadAccess = Depends(
    abac(_tenant_resource_id, required_roles=_TASK_READ_ROLES, action="read tasks")
)
TaskWriteAccess = Depends(
    abac(_tenant_resource_id, required_roles=_TASK_WRITE_ROLES, action="manage tasks")
)


def _task_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(code="TASK_VALIDATION_ERROR", message=message, error_type="tasks"),
    )


def _task_not_found(*, code: str = "TASK_NOT_FOUND", message: str = "Task not found") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(code=code, message=message, error_type="tasks"),
    )


def _normalize_meta_value(value):
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


@router.get("/pipeline-runs/{run_id}", response_model=TaskStatusResponse)
async def get_pipeline_run_status(
    run_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = TaskAccess,
) -> TaskStatusResponse:
    """Статус фонового прогона (PipelineRun / Celery). Не путать с obligation Task."""

    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(PipelineRun).where(
        PipelineRun.id == run_id,
        PipelineRun.tenant_id == tenant.id,
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        # Do not leak Celery task existence across tenants.
        raise _task_not_found(code="PIPELINE_RUN_NOT_FOUND")
    metadata: dict[str, object] = {}
    document_id: str | None = None
    result_payload: dict[str, object] | None = None
    status_value: str | None = None
    error_value: str | None = None

    if run is not None:
        metadata = dict(run.result_metadata or {})
        outputs = dict(run.outputs or {})
        if outputs:
            metadata.setdefault("outputs", outputs)
        pipeline_status = (
            run.status.value if hasattr(run.status, "value") else str(run.status)
        )
        metadata.setdefault("pipeline_status", pipeline_status)
        raw_document_id = metadata.get("document_id") or outputs.get("document_id")
        document_id = raw_document_id if isinstance(raw_document_id, str) else None
        status_value = pipeline_status
        error_value = run.error

    celery_state: str | None = None
    if celery_app is not None:
        try:
            async_result = AsyncResult(run_id, app=celery_app)
            celery_state = (async_result.state or "PENDING").upper()
            celery_ready = async_result.ready()
            celery_info = getattr(async_result, "result", None)
        except Exception as exc:  # pragma: no cover - best effort diagnostics
            metadata.setdefault("celery_status", "unavailable")
            metadata["celery_error"] = str(exc)
        else:
            metadata["celery_status"] = celery_state
            metadata["celery_ready"] = celery_ready
            normalized_info = _normalize_meta_value(celery_info)
            if normalized_info is not None:
                metadata["celery_info"] = normalized_info
            if celery_state == "SUCCESS" and isinstance(celery_info, dict):
                result_payload = celery_info
                raw_status = result_payload.get("status")
                if isinstance(raw_status, str) and raw_status:
                    status_value = raw_status
                else:
                    status_value = celery_state
            elif status_value is None:
                status_value = celery_state
            if celery_state == "FAILURE" and celery_info is not None:
                error_value = str(celery_info)

    if result_payload is not None:
        task_tenant = result_payload.get("tenant")
        if task_tenant is not None and (not isinstance(task_tenant, str) or task_tenant != tenant.slug):
            raise _task_not_found(code="PIPELINE_RUN_NOT_FOUND")

    if status_value is None:
        raise _task_not_found(code="PIPELINE_RUN_NOT_FOUND")

    return TaskStatusResponse(
        task_id=run_id,
        status=status_value,
        document_id=document_id,
        error=error_value,
        metadata=metadata or None,
        result=result_payload,
    )


def _normalize_task_status(value: str | None) -> TaskStatus | None:
    if value is None:
        return None
    try:
        return TaskStatus(str(value).lower())
    except ValueError as exc:
        raise _task_unprocessable("Unsupported task status") from exc


def _normalize_task_priority(value: str | None) -> TaskPriority | None:
    if value is None:
        return None
    try:
        return TaskPriority(str(value).lower())
    except ValueError as exc:
        raise _task_unprocessable("Unsupported task priority") from exc


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _task_is_overdue(task: Task, now: datetime) -> bool:
    due_at = _normalize_datetime(task.due_at)
    if due_at is None:
        return False
    if task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}:
        return False
    return due_at < now


def _task_read(task: Task, now: datetime) -> TaskRead:
    return TaskRead.model_validate(
        {
            **TaskRead.model_validate(task).model_dump(),
            "overdue": _task_is_overdue(task, now),
        }
    )


@router.get("", response_model=TaskListResponse)
async def list_tasks(
    request: Request,
    response: Response,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = TaskReadAccess,
    status_value: str | None = Query(default=None, alias="status"),
    priority_value: str | None = Query(default=None, alias="priority"),
    overdue: bool | None = Query(default=None),
    assignee: str | None = Query(default=None, alias="assignee"),
    task_type: str | None = Query(default=None, alias="type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> TaskListResponse | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Task).where(Task.tenant_id == tenant.id)
    status_filter = _normalize_task_status(status_value)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    priority_filter = _normalize_task_priority(priority_value)
    if priority_filter:
        stmt = stmt.where(Task.priority == priority_filter)
    if assignee:
        stmt = stmt.where(Task.assignee_id == assignee)
    if task_type:
        stmt = stmt.where(Task.entity_type == task_type)
    if access.user.role.value == "worker":
        stmt = stmt.where(Task.assignee_id == access.user.id)
    now = datetime.now(timezone.utc)
    if overdue is True:
        stmt = stmt.where(
            Task.due_at.is_not(None),
            Task.due_at < now,
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
        )
    elif overdue is False:
        stmt = stmt.where(
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
        )

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    tasks = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    items = [_task_read(task, now) for task in tasks]
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("page", page), ("page_size", page_size), ("total", int(total or 0))],
    )
    response.headers["ETag"] = etag
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return TaskListResponse(
        items=items,
        pagination=TaskPagination(page=page, page_size=page_size, total=int(total or 0)),
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    request: Request,
    payload: TaskCreate,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = TaskWriteAccess,
) -> TaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    priority = _normalize_task_priority(payload.priority) or TaskPriority.MEDIUM
    task = Task(
        tenant_id=str(tenant.id),
        title=payload.title,
        description=payload.description,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        due_at=payload.due_at,
        assignee_id=payload.assignee_id,
        created_by=getattr(access.user, "id", None),
        priority=priority,
    )
    task.next_remind_at = await next_task_reminder(session, due_at=task.due_at)
    session.add(task)
    await session.flush()
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="task",
        object_id=task.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"entity_type": task.entity_type, "entity_id": task.entity_id},
    )
    await session.commit()
    await session.refresh(task)
    return _task_read(task, datetime.now(timezone.utc))


@router.get("/{task_id}", response_model=TaskRead)
async def get_obligation_task(
    task_id: str,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = TaskReadAccess,
) -> TaskRead:
    """Задача обязательств (obligations). Статус пайплайна — `GET /tasks/pipeline-runs/{run_id}`."""

    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Task).where(Task.id == task_id, Task.tenant_id == tenant.id)
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise _task_not_found(code="OBLIGATION_TASK_NOT_FOUND")

    if access.user.role.value == "worker" and task.assignee_id != access.user.id:
        raise _task_not_found(code="OBLIGATION_TASK_NOT_FOUND")

    return _task_read(task, datetime.now(timezone.utc))


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    request: Request,
    task_id: str,
    payload: TaskUpdate,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = TaskReadAccess,
) -> TaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(Task).where(Task.id == task_id, Task.tenant_id == tenant.id)
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        raise _task_not_found(code="OBLIGATION_TASK_NOT_FOUND")

    if access.user.role.value == "worker":
        if task.assignee_id != access.user.id:
            raise _task_not_found(code="OBLIGATION_TASK_NOT_FOUND")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="FORBIDDEN", message="Workers cannot modify tasks", error_type="tasks"
            ),
        )

    updates = payload.model_dump(exclude_unset=True)
    status_value = _normalize_task_status(updates.pop("status", None))
    if status_value is not None:
        task.status = status_value
        if status_value == TaskStatus.DONE:
            task.completed_at = datetime.now(timezone.utc)
        else:
            task.completed_at = None
    priority_value = _normalize_task_priority(updates.pop("priority", None))
    if priority_value is not None:
        task.priority = priority_value

    for key, value in updates.items():
        setattr(task, key, value)

    task.next_remind_at = await next_task_reminder(session, due_at=task.due_at)
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="task",
        object_id=task.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": task.status.value, "priority": task.priority.value},
    )
    await session.commit()
    await session.refresh(task)
    return _task_read(task, datetime.now(timezone.utc))
