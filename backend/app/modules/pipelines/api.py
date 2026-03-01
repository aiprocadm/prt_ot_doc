from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
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


def _serialize_profile(model) -> PipelineProfileRead:
    step_payload = []
    for step in (model.steps or []):
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
    )

def _serialize_step(step: DocumentJobStep) -> dict[str, Any]:
    return {
        "step_run_id": step.id,
        "run_id": step.job_id,
        "step_code": step.step_code,
        "status": str(step.status),
        "attempt": step.attempts,
        "started_at": step.started_at,
        "ended_at": step.ended_at,
        "error_code": step.error_code,
        "error_payload": step.error_payload,
        "input": step.input,
        "output": step.output,
    }


async def _build_run_read(session: AsyncSession, run: DocumentJob) -> PipelineRunRead:
    steps = (
        await session.execute(
            select(DocumentJobStep)
            .where(DocumentJobStep.job_id == run.id)
            .order_by(DocumentJobStep.order.asc())
        )
    ).scalars().all()
    return PipelineRunRead(
        run_id=run.id,
        profile_id=run.profile_id or run.pipeline_profile_id,
        status=str(run.status),
        inputs_json=run.input,
        outputs_json=run.output,
        created_by=run.created_by,
        correlation_id=run.correlation_id,
        step_runs=[PipelineStepRunRead(**_serialize_step(step)) for step in steps],
    )


@router.post("/profiles", response_model=PipelineProfileRead, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: PipelineProfileCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    try:
        model = await repo.create(tenant_id=str(tenant.id), payload=payload)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "profile code already exists") from exc
    return _serialize_profile(model)


@router.get("/profiles", response_model=list[PipelineProfileRead])
async def list_profiles(active: bool | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> list[PipelineProfileRead]:
    rows = await PipelineProfileRepo(session).list(tenant_id=str(tenant.id), active=active)
    return [_serialize_profile(r) for r in rows]


@router.get("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def get_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    model = await PipelineProfileRepo(session).get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return _serialize_profile(model)


@router.patch("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def patch_profile(profile_id: str, payload: PipelineProfilePatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    await repo.patch(model=model, payload=payload)
    await session.commit()
    return _serialize_profile(model)


@router.put("/profiles/{profile_id}", response_model=PipelineProfileRead)
async def put_profile(profile_id: str, payload: PipelineProfilePatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    return await patch_profile(profile_id=profile_id, payload=payload, session=session, tenant=tenant)


@router.post("/profiles/{profile_id}:activate", response_model=PipelineProfileRead)
async def activate_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineProfileRead:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    model.is_active = True
    await session.commit()
    return _serialize_profile(model)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_profile(profile_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> None:
    repo = PipelineProfileRepo(session)
    model = await repo.get(tenant_id=str(tenant.id), profile_id=profile_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    active_job = (
        await session.execute(select(DocumentJob).where(DocumentJob.tenant_id == str(tenant.id), DocumentJob.profile_id == profile_id, DocumentJob.status.in_(["queued", "running"])))
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
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> PipelineRunAccepted:
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")

    repo = PipelineProfileRepo(session)
    profile = None
    if payload.profile_id:
        profile = await repo.get(tenant_id=str(tenant.id), profile_id=payload.profile_id)
    elif payload.profile_code:
        profile = await repo.get_by_code(tenant_id=str(tenant.id), code=payload.profile_code)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    request_hash = compute_request_hash(payload.model_dump())
    idem_service = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="pipelines.runs")
    idem_key = normalize_idempotency_key(idempotency_key)
    record, created = await idem_service.acquire(key=idem_key, request_hash=request_hash, method="POST", path="/v1/pipelines/runs")
    if not created:
        return await idem_service.respond_from_store(record, model=PipelineRunAccepted, response=response)

    orchestrator = DocumentPipelineOrchestrator(session)
    job = await orchestrator.start_document_job(
        tenant_id=str(tenant.id),
        created_by=None,
        payload={
            "template_code": profile.code,
            "template_version": 1,
            "pipeline_profile_id": profile.id,
            "input": payload.inputs,
            "options": payload.options or {},
        },
        idempotency_key=idem_key,
        request_hash=request_hash,
    )
    job.profile_id = profile.id
    job.input = payload.inputs
    await session.flush()
    steps = (await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
    accepted = PipelineRunAccepted(run_id=job.id, status=str(job.status), step_runs=[_serialize_step(s) for s in steps])
    await idem_service.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=accepted.model_dump())
    await session.commit()
    return accepted


@router.get("/runs", response_model=list[PipelineRunRead])
async def list_runs(
    status_filter: str | None = Query(default=None, alias="status"),
    profile: str | None = Query(default=None),
    created_by: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> list[PipelineRunRead]:
    stmt = select(DocumentJob).where(DocumentJob.tenant_id == str(tenant.id)).order_by(DocumentJob.updated_at.desc())
    if status_filter:
        stmt = stmt.where(DocumentJob.status == status_filter)
    if profile:
        stmt = stmt.where((DocumentJob.profile_id == profile) | (DocumentJob.pipeline_profile_id == profile) | (DocumentJob.template_code == profile))
    if created_by:
        stmt = stmt.where(DocumentJob.created_by == created_by)
    if q:
        stmt = stmt.where((DocumentJob.template_code.ilike(f"%{q}%")) | (DocumentJob.correlation_id.ilike(f"%{q}%")))
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
async def get_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return await _build_run_read(session, run)


@router.post("/runs/{run_id}:cancel", response_model=PipelineRunRead)
async def cancel_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    await DocumentPipelineOrchestrator(session).cancel_job(job_id=run_id)
    await session.commit()
    return await _build_run_read(session, run)


@router.post("/runs/{run_id}:retry", response_model=PipelineRunRead)
async def retry_run(run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    await DocumentPipelineOrchestrator(session).retry_job(job_id=run_id, retry_failed_only=True)
    await session.commit()
    return await _build_run_read(session, run)


@router.post("/runs/{run_id}/steps/{step_run_id}:retry", response_model=PipelineRunRead)
async def retry_step_run(run_id: str, step_run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> PipelineRunRead:
    run = await session.get(DocumentJob, run_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    step = await session.get(DocumentJobStep, step_run_id)
    if step is None or step.job_id != run_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "step run not found")
    await DocumentPipelineOrchestrator(session).retry_step(job_id=run_id, step_code=step.step_code)
    await session.commit()
    return await _build_run_read(session, run)


@router.post("/run", response_model=PipelineRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline_compat(
    payload: PipelineRunRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> PipelineRunAccepted:
    return await run_pipeline(payload=payload, response=response, idempotency_key=idempotency_key, session=session, tenant=tenant)
