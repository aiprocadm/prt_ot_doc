from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobStep
from app.models.models import Tenant
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepRead(BaseModel):
    code: str
    status: str
    attempt: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    input_ref: dict[str, Any] | None = None
    output_ref: dict[str, Any] | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


class JobEnvelopeRead(BaseModel):
    id: str
    status: str
    correlation_id: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    error_code: str | None = None
    error_payload: dict[str, Any] | None = None


class JobRead(BaseModel):
    job: JobEnvelopeRead
    steps: list[JobStepRead]
    result: dict[str, Any] | None = None


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    steps = (
        await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.created_at.asc()))
    ).scalars().all()
    artifacts = (
        await session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job.id).order_by(DocumentArtifact.created_at.asc()))
    ).scalars().all()
    return JobRead(
        job=JobEnvelopeRead(
            id=job.id,
            status=str(job.status),
            started_at=job.started_at,
            ended_at=job.ended_at,
            error_code=job.error_code,
            error_payload=job.error_payload,
            correlation_id=job.correlation_id,
        ),
        steps=[
            JobStepRead(
                code=s.step_code,
                status=str(s.status),
                attempt=s.attempts,
                started_at=s.started_at,
                ended_at=s.ended_at,
                input_ref=s.input_ref,
                output_ref=s.output_ref,
                error_code=s.error_code,
                error_payload=s.error_payload,
            )
            for s in steps
        ],
        result={
            "document_version_id": job.result_document_version_id,
            "files": [{"file_id": a.file_id, "step_code": a.step_code, "kind": a.kind, "sha256": a.sha256} for a in artifacts],
        }
        if artifacts or job.result_document_version_id
        else None,
    )


@router.post("/{job_id}:cancel", response_model=JobRead)
async def cancel_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    orchestrator = DocumentPipelineOrchestrator(session)
    await orchestrator.cancel_job(job_id=job_id)
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)


@router.post("/{job_id}/retry", response_model=JobRead)
async def retry_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is None or str(job.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    orchestrator = DocumentPipelineOrchestrator(session)
    try:
        await orchestrator.retry_job(job_id=job_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    return await get_job(job_id=job_id, session=session, tenant=tenant)
