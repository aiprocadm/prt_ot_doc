from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.core.security import AccessContext, abac
from app.models.job_engine import DocumentJob, DocumentJobStep
from app.models.models import Tenant
from app.modules.pipelines.repo import PipelineProfileRepo
from app.modules.pipelines.schemas import (
    PipelineProfileCreate,
    PipelineProfilePatch,
    PipelineProfileRead,
    PipelineRunAccepted,
    PipelineRunRead,
    PipelineRunRequest,
    PipelineStepRunRead,
)
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_PIPELINES_READ_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "manager",
    "line_manager",
    "auditor_ro",
]
_PIPELINES_WRITE_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "manager",
]

PipelinesReadAccess = Depends(
    abac(_tenant_resource_id, required_roles=_PIPELINES_READ_ROLES, action="read pipelines")
)
PipelinesWriteAccess = Depends(
    abac(_tenant_resource_id, required_roles=_PIPELINES_WRITE_ROLES, action="manage pipelines")
)


def _serialize_profile(model) -> PipelineProfileRead:
    step_payload = []
    for step in model.steps or []:
        if isinstance(step, dict) and "code" in step and "params_schema" in step:
            step_payload.append(step)
    return PipelineProfileRead(
        id=model.id,
        code=model.code,
        name=model.name,
        description=getattr(model, "description", None),
        is_active=model.is_active,
        steps=step_payload,
        graph=getattr(model, "graph", None) or None,
        limits=model.limits or {},
        profile_version=getattr(model, "profile_version", 1),
        version=model.version,
        concurrency_limit_per_tenant=getattr(model, "concurrency_limit_per_tenant", None),
    )


def _serialize_step(step: DocumentJobStep) -> dict[str, Any]:
    return {
        "step_run_id": step.id,
        "run_id": step.job_id,
        "step_code": step.step_code,
        "status": step.status.value if hasattr(step.status, "value") else str(step.status),
        "attempt": step.attempt,
        "started_at": step.started_at,
        "ended_at": step.ended_at,
        "error_code": step.error_code,
        "error_payload": step.error_payload,
        "max_attempts": step.max_attempts,
        "logs_ref": step.logs_ref,
        "input": step.input,
        "output": step.output,
    }


async def _build_run_read(session: AsyncSession, run: DocumentJob) -> PipelineRunRead:
    steps = (
        (
            await session.execute(
                select(DocumentJobStep)
                .where(DocumentJobStep.job_id == run.id)
                .order_by(DocumentJobStep.seq.asc().nullslast(), DocumentJobStep.order.asc())
            )
        )
        .scalars()
        .all()
    )
    return PipelineRunRead(
        run_id=run.id,
        profile_id=run.profile_id or run.pipeline_profile_id,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        inputs_json=run.input,
        outputs_json=run.output,
        created_by=run.created_by,
        correlation_id=run.correlation_id,
        step_runs=[PipelineStepRunRead(**_serialize_step(step)) for step in steps],
    )


def _run_snapshot_hash(run_payload: PipelineRunRead) -> str:
    body = json.dumps(run_payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(
        body.encode("utf-8"), usedforsecurity=False
    ).hexdigest()  # nosec B324 - run-snapshot fingerprint, not security


@router.post("/profiles", response_model=PipelineProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: PipelineProfileCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    try:
        model = await repo.create(tenant_id=str(tenant.id), payload=payload)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "profile code already exists") from exc
    return _serialize_profile(model)


@router.get("/profiles", response_model=list[PipelineProfileRead])
async def list_profiles(
    active: bool | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesReadAccess,
) -> list[PipelineProfileRead]:
    rows = await PipelineProfileRepo(session).list(tenant_id=str(tenant.id), active=active)
    return [_serialize_profile(r) for r in rows]


@router.get("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def get_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesReadAccess,
) -> PipelineProfileRead:
    model = await PipelineProfileRepo(session).get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return _serialize_profile(model)


@router.patch("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def patch_profile(
    profile_id: str,
    payload: PipelineProfilePatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    await repo.patch(model=model, payload=payload)
    await session.commit()
    return _serialize_profile(model)


@router.put("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def put_profile(
    profile_id: str,
    payload: PipelineProfilePatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineProfileRead:
    return await patch_profile(
        profile_id=profile_id, payload=payload, session=session, tenant=tenant
    )


@router.post("/profiles/{profile_id}:activate", response_model=PipelineProfileRead)
async def activate_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    model.is_active = True
    await session.commit()
    return _serialize_profile(model)


@router.delete(
    "/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> None:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    active_job = (
        await session.execute(
            select(DocumentJob).where(
                DocumentJob.tenant_id == str(tenant.id),
                DocumentJob.profile_id == profile_id,
                DocumentJob.status.in_(["queued", "running"]),
            )
        )
    ).scalar_one_or_none()
    if active_job:
        raise HTTPException(status.HTTP_409_CONFLICT, "profile has active jobs")
    await repo.soft_delete(model=model)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs", response_model=PipelineRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    payload: PipelineRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineRunAccepted:
    if not x_tenant:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant is required")
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")

    repo = PipelineProfileRepo(session)
    profile = None
    requested_profile_id = payload.profile_id or payload.pipeline_profile_id
    requested_profile_code = payload.profile_code or payload.pipeline_profile_code
    if requested_profile_id:
        profile = await repo.get(tenant_id=str(tenant.id), profile_id=requested_profile_id)
    elif requested_profile_code:
        profile = await repo.get_by_code(tenant_id=str(tenant.id), code=requested_profile_code)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    request_payload = payload.model_dump(mode="json")
    request_hash = compute_request_hash(
        {"tenant_id": str(tenant.id), "endpoint": "/api/v1/pipelines/run", "body": request_payload}
    )
    idem_service = IdempotencyService(
        session=session, tenant_id=str(tenant.id), endpoint="pipelines.runs"
    )
    idem_key = normalize_idempotency_key(idempotency_key)
    record, created = await idem_service.acquire(
        key=idem_key, request_hash=request_hash, method="POST", path="/api/v1/pipelines/run"
    )
    if not created:
        return await idem_service.respond_from_store(
            record, model=PipelineRunAccepted, response=response
        )

    orchestrator = DocumentPipelineOrchestrator(session)
    job = await orchestrator.start_document_job(
        tenant_id=str(tenant.id),
        created_by=None,
        payload={
            "template_code": profile.code,
            "template_version": 1,
            "pipeline_profile_id": profile.id,
            "input": payload.inputs,
            "sources": payload.sources,
            "template_versions": payload.template_versions,
            "header_preset_id": payload.header_preset_id,
            "replace_map_file_id": payload.replace_map_file_id,
            "naming_template": payload.naming_template,
            "options": {
                **(payload.options or {}),
                "preset_id": payload.preset_id,
            },
        },
        idempotency_key=idem_key,
        request_hash=request_hash,
    )
    steps = (
        (
            await session.execute(
                select(DocumentJobStep)
                .where(DocumentJobStep.job_id == job.id)
                .order_by(DocumentJobStep.seq.asc().nullslast(), DocumentJobStep.order.asc())
            )
        )
        .scalars()
        .all()
    )
    accepted = PipelineRunAccepted(
        run_id=job.id,
        job_id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        correlation_id=job.correlation_id,
        step_runs=[_serialize_step(s) for s in steps],
    )
    await idem_service.store_success(
        record, status_code=status.HTTP_202_ACCEPTED, body=accepted.model_dump(mode="json")
    )
    await session.commit()
    return accepted


@router.post("/run", response_model=PipelineRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline_compat(
    payload: PipelineRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineRunAccepted:
    return await run_pipeline(
        payload=payload,
        response=response,
        idempotency_key=idempotency_key,
        x_tenant=x_tenant,
        session=session,
        tenant=tenant,
    )


@router.get("/runs", response_model=list[PipelineRunRead])
async def list_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    profile: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesReadAccess,
) -> list[PipelineRunRead]:
    stmt = (
        select(DocumentJob)
        .where(DocumentJob.tenant_id == str(tenant.id))
        .order_by(DocumentJob.updated_at.desc())
    )
    if status_filter:
        stmt = stmt.where(DocumentJob.status == status_filter)
    if profile:
        stmt = stmt.where(
            (DocumentJob.profile_id == profile)
            | (DocumentJob.pipeline_profile_id == profile)
            | (DocumentJob.template_code == profile)
        )
    if created_by:
        stmt = stmt.where(DocumentJob.created_by == created_by)
    if q:
        stmt = stmt.where(
            (DocumentJob.template_code.ilike(f"%{q}%"))
            | (DocumentJob.correlation_id.ilike(f"%{q}%"))
        )
    if date_from:
        stmt = stmt.where(DocumentJob.created_at >= date_from)
    runs = (await session.execute(stmt)).scalars().all()
    return [await _build_run_read(session, run) for run in runs]


@router.post("/runs:bulk", response_model=list[PipelineRunRead])
async def bulk_update_runs(
    run_ids: list[str],
    action: str = Query(pattern="^(retry|cancel)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> list[PipelineRunRead]:
    orchestrator = DocumentPipelineOrchestrator(session)
    updated: list[PipelineRunRead] = []
    for run_id in run_ids:
        run = await session.get(DocumentJob, run_id)
        if run is None or str(run.tenant_id) != str(tenant.id):
            continue
        if action == "retry":
            await orchestrator.retry_job(job_id=run.id, retry_failed_only=True)
        else:
            await orchestrator.cancel_job(job_id=run.id)
        updated.append(await _build_run_read(session, run))
    await session.commit()
    return updated


@router.get("/runs/{run_id}", response_model=PipelineRunRead)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesReadAccess,
) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return await _build_run_read(session, run)


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesReadAccess,
) -> StreamingResponse:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")

    async def _stream() -> Any:
        previous_hash: str | None = None
        while True:
            run_obj = await session.get(DocumentJob, run_id)
            if run_obj is None or str(run_obj.tenant_id) != str(tenant.id):
                break
            payload = await _build_run_read(session, run_obj)
            snapshot_hash = _run_snapshot_hash(payload)
            if snapshot_hash != previous_hash:
                previous_hash = snapshot_hash
                yield "event: run.update\n"
                yield f"data: {json.dumps(payload.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            current_status = (
                run_obj.status.value if hasattr(run_obj.status, "value") else str(run_obj.status)
            )
            if current_status in {"success", "failed", "canceled"}:
                yield "event: run.done\n"
                yield f"data: {json.dumps(payload.model_dump(mode='json'), ensure_ascii=False)}\n\n"
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(2)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(_stream(), media_type="text/event-stream", headers=headers)


@router.post("/runs/{run_id}:cancel", response_model=PipelineRunRead)
async def cancel_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    await DocumentPipelineOrchestrator(session).cancel_job(job_id=run_id)
    await session.commit()
    return await _build_run_read(session, run)


@router.post("/runs/{run_id}:retry", response_model=PipelineRunRead)
async def retry_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    await DocumentPipelineOrchestrator(session).retry_job(job_id=run_id, retry_failed_only=True)
    await session.commit()
    return await _build_run_read(session, run)


@router.post("/runs/{run_id}/steps/{step_run_id}:retry", response_model=PipelineRunRead)
async def retry_step_run(
    run_id: str,
    step_run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = PipelinesWriteAccess,
) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    step = await session.get(DocumentJobStep, step_run_id)
    if step is None or step.job_id != run_id or str(step.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "step run not found")
    await DocumentPipelineOrchestrator(session).retry_step(job_id=run_id, step_code=step.step_code)
    await session.commit()
    return await _build_run_read(session, run)
