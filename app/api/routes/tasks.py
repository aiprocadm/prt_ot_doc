"""Generic task inspection endpoints."""
from __future__ import annotations

from uuid import UUID

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import PipelineRun, Tenant
from app.schemas.task import TaskStatusResponse
from app.services.celery_app import celery_app

router = APIRouter()

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


TaskAccess = Depends(
    abac(_tenant_resource_id, required_roles=["admin"], action="inspect tasks")
)


def _normalize_meta_value(value):
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = TaskAccess,
) -> TaskStatusResponse:
    stmt = select(PipelineRun).where(
        PipelineRun.id == task_id,
        PipelineRun.tenant_id == tenant.id,
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
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
        document_id = metadata.get("document_id") or outputs.get("document_id")
        status_value = pipeline_status
        error_value = run.error

    celery_state: str | None = None
    if celery_app is not None:
        try:
            async_result = AsyncResult(task_id, app=celery_app)
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
                status_value = result_payload.get("status") or celery_state
            elif status_value is None:
                status_value = celery_state
            if celery_state == "FAILURE" and celery_info is not None:
                error_value = str(celery_info)

    if result_payload is not None:
        task_tenant = result_payload.get("tenant") if isinstance(result_payload, dict) else None
        if task_tenant and task_tenant != tenant.slug:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")

    if status_value is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")

    return TaskStatusResponse(
        task_id=task_id,
        status=status_value,
        document_id=document_id,
        error=error_value,
        metadata=metadata or None,
        result=result_payload,
    )
