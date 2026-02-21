from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobStep
from app.models.models import PipelineRun, PipelineRunStatus, Tenant
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepRead(BaseModel):
    name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    retries_count: int = 0


class JobRead(BaseModel):
    id: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    correlation_id: str | None = None
    steps: list[JobStepRead]
    artifacts: list[dict] = []


class JobArtifactsRead(BaseModel):
    job_id: str
    docx_storage_key: str | None = None
    pdf_storage_key: str | None = None
    zip_storage_key: str | None = None


def _default_steps(run: PipelineRun) -> list[JobStepRead]:
    if run.status == PipelineRunStatus.DONE:
        state = "done"
    elif run.status == PipelineRunStatus.ERROR:
        state = "error"
    elif run.status == PipelineRunStatus.RUNNING:
        state = "running"
    else:
        state = "queued"
    return [
        JobStepRead(name="render_docx", status=state, started_at=run.started_at, finished_at=run.finished_at),
        JobStepRead(name="apply_headers", status="done" if state == "done" else "skipped"),
        JobStepRead(name="replace", status="done" if state == "done" else "skipped"),
        JobStepRead(name="convert_pdf", status="done" if state == "done" else "pending"),
    ]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobRead:
    job = await session.get(DocumentJob, job_id)
    if job is not None and str(job.tenant_id) == str(tenant.id):
        steps = (
            await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id))
        ).scalars().all()
        artifacts = (
            await session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job.id))
        ).scalars().all()
        return JobRead(
            id=job.id,
            status=str(job.status),
            started_at=job.started_at,
            finished_at=job.ended_at,
            error=job.error_code,
            correlation_id=job.correlation_id,
            steps=[
                JobStepRead(
                    name=s.step_code,
                    status=str(s.status),
                    started_at=s.started_at,
                    finished_at=s.ended_at,
                    error=s.error_code,
                    retries_count=s.attempts,
                )
                for s in steps
            ],
            artifacts=[{"step_code": a.step_code, "kind": a.kind, "sha256": a.sha256} for a in artifacts],
        )

    run = await session.get(PipelineRun, job_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")

    return JobRead(
        id=run.id,
        status=run.status.value,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        steps=_default_steps(run),
    )


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


@router.get("/{job_id}/artifacts", response_model=JobArtifactsRead)
async def get_job_artifacts(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> JobArtifactsRead:
    run = await session.get(PipelineRun, job_id)
    if run is None or str(run.tenant_id) != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    metadata = run.result_metadata or {}
    outputs = run.outputs or {}
    return JobArtifactsRead(
        job_id=run.id,
        docx_storage_key=run.docx_storage_key or metadata.get("docx_storage_key"),
        pdf_storage_key=run.pdf_storage_key or metadata.get("pdf_storage_key"),
        zip_storage_key=outputs.get("zip_storage_key") or metadata.get("zip_storage_key"),
    )
