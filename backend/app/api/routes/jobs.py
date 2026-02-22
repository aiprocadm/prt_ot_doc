from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobLog, DocumentJobStep
from app.models.models import Tenant
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepRead(BaseModel):
    code: str
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


class JobListRead(BaseModel):
    items: list[JobEnvelopeRead]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    steps = (await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
    artifacts = (await session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job.id).order_by(DocumentArtifact.created_at.asc()))).scalars().all()
    logs = (await session.execute(select(DocumentJobLog).where(DocumentJobLog.job_id == job.id).order_by(DocumentJobLog.created_at.asc()))).scalars().all()
    return JobRead(
        job=JobEnvelopeRead(
            id=job.id,
            status=str(job.status),
            started_at=job.started_at,
            ended_at=job.ended_at,
            error_code=job.error_code,
            error_payload=job.error_payload,
            correlation_id=job.correlation_id,
            profile_id=job.profile_id or job.pipeline_profile_id,
            created_by=job.created_by,
        ),
        steps=[JobStepRead(code=s.step_code, status=str(s.status), attempt=s.attempts, max_attempts=s.max_attempts, started_at=s.started_at, ended_at=s.ended_at, input_ref=s.input_ref, output_ref=s.output_ref, error_code=s.error_code, error_payload=s.error_payload) for s in steps],
        logs=[JobLogRead(timestamp=l.created_at, level=l.level, message=l.message, step_name=l.step_code, meta_json=l.meta_json) for l in logs],
        result={"document_version_id": job.result_document_version_id, "files": [{"file_id": a.file_id, "step_code": a.step_code, "kind": a.kind, "sha256": a.sha256} for a in artifacts]} if artifacts or job.result_document_version_id else None,
    )


@router.get("", response_model=JobListRead)
async def list_jobs(
    status_filter: str | None = Query(default=None, alias="status"),
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
    if template_code:
        stmt = stmt.where(DocumentJob.template_code == template_code)
    if project_id:
        stmt = stmt.where(DocumentJob.preset_id == project_id)
    if created_from:
        stmt = stmt.where(DocumentJob.created_at >= created_from)
    if created_to:
        stmt = stmt.where(DocumentJob.created_at <= created_to)
    rows = (await session.execute(stmt.order_by(DocumentJob.updated_at.desc()))).scalars().all()
    return JobListRead(items=[JobEnvelopeRead(id=job.id, status=str(job.status), correlation_id=job.correlation_id, started_at=job.started_at, ended_at=job.ended_at, error_code=job.error_code, error_payload=job.error_payload, profile_id=job.profile_id or job.pipeline_profile_id, created_by=job.created_by) for job in rows])


@router.post("/{job_id}:cancel", response_model=JobRead)
async def cancel_job(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    await DocumentPipelineOrchestrator(session).cancel_job(job_id=job_id)
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)


class RetryJobRequest(BaseModel):
    retry_failed_only: bool = False


@router.post("/{job_id}:retry", response_model=JobRead)
@router.post("/{job_id}/retry", response_model=JobRead)
async def retry_job(job_id: str, payload: RetryJobRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    try:
        await DocumentPipelineOrchestrator(session).retry_job(job_id=job_id, retry_failed_only=payload.retry_failed_only)
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


class RetryStepRequest(BaseModel):
    step_key: str


@router.post("/{job_id}:retry-step", response_model=JobRead)
async def retry_step_compat(job_id: str, payload: RetryStepRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> JobRead:
    return await rerun_step(job_id=job_id, step=payload.step_key, session=session, tenant=tenant)
