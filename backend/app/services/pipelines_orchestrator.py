from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
    OutboxEvent,
)

MANDATORY_STEPS = ["render_docx", "apply_headers", "replace", "convert_pdf"]
OPTIONAL_STEPS = ["build_zip", "send_edo", "archive"]


class DocumentPipelineOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_document_job(self, *, tenant_id: str, created_by: str | None, payload: dict[str, Any]) -> DocumentJob:
        profile_id = payload.get("pipeline_profile_id")
        options = payload.get("options") or {}
        optional_steps: list[str] = []
        if options.get("zip"):
            optional_steps.append("build_zip")
        if options.get("edo"):
            optional_steps.append("send_edo")
        if options.get("archive"):
            optional_steps.append("archive")

        job = DocumentJob(
            tenant_id=tenant_id,
            status=DocumentJobStatus.QUEUED.value,
            pipeline_profile_id=profile_id,
            template_code=payload["template_code"],
            template_version=payload.get("template_version"),
            correlation_id=str(uuid4()),
            created_by=created_by,
        )
        self.session.add(job)
        await self.session.flush()

        for step in [*MANDATORY_STEPS, *optional_steps]:
            self.session.add(
                DocumentJobStep(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    step_code=step,
                    status=JobStepStatus.QUEUED.value,
                )
            )
        await self.session.flush()
        return job

    async def run_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")

        job.status = DocumentJobStatus.RUNNING.value
        job.started_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

        steps = (
            await self.session.execute(
                select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.created_at.asc())
            )
        ).scalars().all()

        for step in steps:
            artifact_kind = self._artifact_kind(step.step_code)
            if artifact_kind and await self._artifact_exists(job.id, step.step_code, artifact_kind):
                step.status = JobStepStatus.SUCCESS.value
                step.started_at = step.started_at or datetime.now(tz=timezone.utc)
                step.ended_at = datetime.now(tz=timezone.utc)
                continue

            step.status = JobStepStatus.RUNNING.value
            step.attempts += 1
            step.started_at = datetime.now(tz=timezone.utc)
            await self.session.flush()

            if fail_step and step.step_code == fail_step:
                step.status = JobStepStatus.FAILED.value
                step.error_code = "step_failed"
                step.error_payload = {"step": step.step_code}
                step.ended_at = datetime.now(tz=timezone.utc)
                job.status = DocumentJobStatus.FAILED.value
                job.error_code = step.error_code
                job.error_payload = step.error_payload
                job.ended_at = datetime.now(tz=timezone.utc)
                await self._emit_event(job=job, event_type="Failed", payload={"job_id": job.id, "error_code": job.error_code, "correlation_id": job.correlation_id})
                await self.session.flush()
                return job

            if artifact_kind:
                self.session.add(
                    DocumentArtifact(
                        tenant_id=job.tenant_id,
                        job_id=job.id,
                        step_code=step.step_code,
                        kind=artifact_kind,
                        sha256=(step.step_code.encode("utf-8").hex() + "0" * 64)[:64],
                        meta={"step": step.step_code},
                    )
                )

            step.status = JobStepStatus.SUCCESS.value
            step.ended_at = datetime.now(tz=timezone.utc)

        job.status = DocumentJobStatus.SUCCESS.value
        job.ended_at = datetime.now(tz=timezone.utc)
        await self._emit_event(job=job, event_type="DocumentGenerated", payload={"job_id": job.id, "artifacts": await self._artifact_list(job.id)})
        if any(s.step_code == "build_zip" for s in steps):
            await self._emit_event(job=job, event_type="Exported", payload={"job_id": job.id, "artifacts": await self._artifact_list(job.id)})
        await self.session.flush()
        return job

    async def retry_job(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        if job.status not in {DocumentJobStatus.FAILED.value, DocumentJobStatus.CANCELED.value}:
            raise ValueError("job_not_retryable")
        job.status = DocumentJobStatus.QUEUED.value
        job.error_code = None
        job.error_payload = None
        await self.session.flush()
        return await self.run_job(job_id=job_id)

    async def _emit_event(self, *, job: DocumentJob, event_type: str, payload: dict[str, Any]) -> None:
        self.session.add(
            OutboxEvent(
                tenant_id=job.tenant_id,
                event_type=event_type,
                event_id=str(uuid4()),
                payload={**payload, "tenant_id": job.tenant_id},
            )
        )

    @staticmethod
    def _artifact_kind(step_code: str) -> str | None:
        return {
            "render_docx": "docx",
            "convert_pdf": "pdf",
            "build_zip": "zip",
        }.get(step_code)

    async def _artifact_exists(self, job_id: str, step_code: str, kind: str) -> bool:
        existing = (
            await self.session.execute(
                select(DocumentArtifact).where(
                    DocumentArtifact.job_id == job_id,
                    DocumentArtifact.step_code == step_code,
                    DocumentArtifact.kind == kind,
                )
            )
        ).scalar_one_or_none()
        return existing is not None

    async def _artifact_list(self, job_id: str) -> list[dict[str, Any]]:
        artifacts = (
            await self.session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job_id))
        ).scalars().all()
        return [{"step_code": a.step_code, "kind": a.kind, "sha256": a.sha256} for a in artifacts]
