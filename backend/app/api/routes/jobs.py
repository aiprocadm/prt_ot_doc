from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobLog, DocumentJobStep
from app.models.models import Tenant
from app.modules.pipelines.models import PipelineProfile
from app.modules.files.models import FileRecord
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepRead(BaseModel):
    code: str
    step_name: str
    status: str
    attempt: int = 0
    max_attempts: int = 1
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_ref: dict[str, Any] | None = None
    output_ref: dict[str, Any] | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


class JobLogRead(BaseModel):
    timestamp: datetime
    level: str
    message: str
    step_name: str | None = None
    meta_json: dict[str, Any] | None = None


class JobEnvelopeRead(BaseModel):
    id: str
    kind: str | None = None
    status: str
    correlation_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None
    profile_id: str | None = None
    created_by: str | None = None


class JobRead(BaseModel):
    job: JobEnvelopeRead
    steps: list[JobStepRead]
    logs: list[JobLogRead] = []
    result: dict[str, Any] | None = None


class JobCreateRequest(BaseModel):
    profile_code: str | None = None
    preset_id: str | None = None
    profile_id: str | None = None
    input_payload: dict[str, Any] = {}
    inputs: dict[str, Any] = {}
    options: dict[str, Any] = {}


class JobCreateResponse(BaseModel):
    job_id: str
    status: str
    correlation_id: str
    steps: list[JobStepRead]


def _status_value(raw: Any) -> str:
    return raw.value if hasattr(raw, "value") else str(raw)


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: JobCreateRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JobCreateResponse:
    profile = None
    if payload.profile_id:
        profile = await session.get(PipelineProfile, payload.profile_id)
    elif payload.profile_code:
        profile = (await session.execute(select(PipelineProfile).where(PipelineProfile.tenant_id == str(tenant.id), PipelineProfile.code == payload.profile_code, PipelineProfile.is_active.is_(True)))).scalar_one_or_none()
    if profile is None or str(profile.tenant_id) != str(tenant.id) or not profile.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")

    request_hash = compute_request_hash(payload.model_dump())
    idem_service = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="jobs.create")
    idem_key = normalize_idempotency_key(idempotency_key) if idempotency_key else None
    record = None
    if idem_key:
        record, created = await idem_service.acquire(key=idem_key, request_hash=request_hash, method="POST", path="/v1/jobs")
        if not created:
            body = await idem_service.respond_from_store(record, model=JobCreateResponse)
            return body

    orchestrator = DocumentPipelineOrchestrator(session)
    job = await orchestrator.start_document_job(
        tenant_id=str(tenant.id),
        created_by=None,
        payload={
            "template_code": profile.code,
            "template_version": 1,
            "pipeline_profile_id": profile.id,
            "input": payload.input_payload or payload.inputs,
            "options": {**payload.options, "preset_id": payload.preset_id},
        },
        idempotency_key=idem_key or f"jobs:{tenant.id}:{request_hash[:16]}",
        request_hash=request_hash,
    )
    steps = (await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
    response_body = {
        "job_id": job.id,
        "status": _status_value(job.status),
        "correlation_id": job.correlation_id,
        "steps": [
            {
                "code": s.step_key or s.step_code,
                "step_name": s.step_key or s.step_code,
                "status": _status_value(s.status),
                "attempt": s.attempts,
                "max_attempts": s.max_attempts,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "input_ref": s.input_ref,
                "output_ref": s.output_ref,
                "error_code": s.error_code,
                "error_payload": s.error_payload,
            }
            for s in steps
        ],
    }
    if idem_key and record is not None:
        await idem_service.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=response_body)
    await session.commit()
    return JobCreateResponse.model_validate(response_body)


class JobListRead(BaseModel):
    items: list[JobEnvelopeRead]
    next_cursor: str | None = None


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    steps = (await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
    artifacts = (await session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job.id).order_by(DocumentArtifact.created_at.asc()))).scalars().all()
    logs = (await session.execute(select(DocumentJobLog).where(DocumentJobLog.job_id == job.id).order_by(DocumentJobLog.created_at.asc()))).scalars().all()
    file_ids = [a.file_id for a in artifacts if a.file_id]
    file_rows = {}
    if file_ids:
        file_rows = {
            f.id: f
            for f in (await session.execute(select(FileRecord).where(FileRecord.id.in_(file_ids)))).scalars().all()
        }
    artifact_map = {
        "all": [
            {
                "file_id": a.file_id,
                "step_code": a.step_code,
                "kind": a.kind,
                "sha256": a.sha256,
                "display_name": (file_rows.get(a.file_id).metadata_json or {}).get("display_name") if file_rows.get(a.file_id) else None,
                "size": file_rows.get(a.file_id).size_bytes if file_rows.get(a.file_id) else None,
                "status": file_rows.get(a.file_id).status if file_rows.get(a.file_id) else None,
            }
            for a in artifacts
        ]
    }
    return JobRead(
        job=JobEnvelopeRead(
            id=job.id,
            kind=job.kind,
            status=_status_value(job.status),
            started_at=job.started_at,
            ended_at=job.ended_at,
            error_code=job.error_code,
            error_payload=job.error_payload,
            correlation_id=job.correlation_id,
            profile_id=job.profile_id or job.pipeline_profile_id,
            created_by=job.created_by,
        ),
        steps=[JobStepRead(code=s.step_code, step_name=s.step_code, status=_status_value(s.status), attempt=s.attempts, max_attempts=s.max_attempts, started_at=s.started_at, ended_at=s.ended_at, input_ref=s.input_ref, output_ref=s.output_ref, error_code=s.error_code, error_payload=s.error_payload) for s in steps],
        logs=[JobLogRead(timestamp=l.created_at, level=l.level, message=l.message, step_name=l.step_code, meta_json=l.meta_json) for l in logs],
        result={"document_version_id": job.result_document_version_id, "files": artifact_map["all"], "artifacts": artifact_map} if artifacts or job.result_document_version_id else None,
    )


@router.get("", response_model=JobListRead)
async def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
    job_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    template_code: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobListRead:
    stmt = select(DocumentJob).where(DocumentJob.tenant_id == str(tenant.id))
    if status_filter:
        stmt = stmt.where(DocumentJob.status == status_filter)
    if job_type:
        stmt = stmt.where(DocumentJob.kind == job_type)
    if template_code:
        stmt = stmt.where(DocumentJob.template_code == template_code)
    if project_id:
        stmt = stmt.where(DocumentJob.preset_id == project_id)
    if created_from:
        stmt = stmt.where(DocumentJob.created_at >= created_from)
    if created_to:
        stmt = stmt.where(DocumentJob.created_at <= created_to)
    if cursor:
        stmt = stmt.where(DocumentJob.created_at < datetime.fromisoformat(cursor))
    rows = (await session.execute(stmt.order_by(DocumentJob.created_at.desc()).limit(limit + 1))).scalars().all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1].created_at.isoformat() if rows[limit - 1].created_at else None
        rows = rows[:limit]
    return JobListRead(items=[JobEnvelopeRead(id=job.id, kind=job.kind, status=_status_value(job.status), correlation_id=job.correlation_id, started_at=job.started_at, ended_at=job.ended_at, error_code=job.error_code, error_payload=job.error_payload, profile_id=job.profile_id or job.pipeline_profile_id, created_by=job.created_by) for job in rows], next_cursor=next_cursor)


@router.post("/{job_id}:cancel", response_model=JobRead)
@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await DocumentPipelineOrchestrator(session).cancel_job(job_id=job_id)
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)


class RetryJobRequest(BaseModel):
    step_key: str | None = None
    from_step_key: str | None = None
    retry_failed_only: bool = False


@router.post("/{job_id}:retry", response_model=JobRead)
@router.post("/{job_id}/retry", response_model=JobRead)
async def retry_job(job_id: str, payload: RetryJobRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    try:
        await DocumentPipelineOrchestrator(session).retry_job(job_id=job_id, from_step_key=payload.from_step_key or payload.step_key, retry_failed_only=payload.retry_failed_only)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)


@router.post("/{job_id}/steps/{step}:rerun", response_model=JobRead)
async def rerun_step(job_id: str, step: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    try:
        await DocumentPipelineOrchestrator(session).retry_step(job_id=job_id, step_code=step)
    except ValueError as exc:
        if str(exc) == "step_not_found":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found") from exc
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)


@router.post("/{job_id}/steps/{step_id}:retry", response_model=JobRead)
async def retry_step_by_id(job_id: str, step_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    step = await session.get(DocumentJobStep, step_id)
    if step is None or step.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    return await rerun_step(job_id=job_id, step=step.step_code, session=session, tenant=tenant)




@router.get("/{job_id}/steps/{step_id}/logs")
async def get_step_logs(job_id: str, step_id: str, tail: int = Query(default=200, ge=1, le=2000), session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict[str, Any]:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    step = await session.get(DocumentJobStep, step_id)
    if step is None or step.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Step not found")
    if not step.logs_uri:
        return {"logs_uri": None, "lines": []}

    from app.services.file_storage import FileStorageService

    storage = FileStorageService.default()
    key = step.logs_uri.replace("s3://", "")
    if not storage.has(key):
        return {"logs_uri": step.logs_uri, "lines": []}
    lines = storage.get(key).decode("utf-8").splitlines()[-tail:]
    return {"logs_uri": step.logs_uri, "lines": lines}
class RetryStepRequest(BaseModel):
    step_key: str


@router.post("/{job_id}:retry-step", response_model=JobRead)
async def retry_step_compat(job_id: str, payload: RetryStepRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    return await rerun_step(job_id=job_id, step=payload.step_key, session=session, tenant=tenant)
