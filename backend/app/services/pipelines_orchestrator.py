from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import AuditService, field_level_diff
from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobLog,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
    OutboxEvent,
    OutboxEventStatus,
)

MANDATORY_STEPS = ["render_docx", "apply_headers", "replace", "convert_pdf"]
OPTIONAL_STEPS = ["build_zip", "verify_signature", "send_edo", "archive"]
RETRYABLE_STEPS = {"convert_pdf": 1, "send_edo": 3}


class StepFailureError(RuntimeError):
    def __init__(self, code: str, payload: dict[str, Any], retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.payload = payload
        self.retryable = retryable


class DocumentPipelineOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start_document_job(
        self,
        *,
        tenant_id: str,
        created_by: str | None,
        payload: dict[str, Any],
        idempotency_key: str,
        request_hash: str,
        correlation_id: str | None = None,
    ) -> DocumentJob:
        options = payload.get("options") or {}
        optional_steps: list[str] = []
        for code in OPTIONAL_STEPS:
            opt_key = code.replace("verify_signature", "sign").replace("send_edo", "edo")
            if options.get(opt_key) or options.get(code):
                optional_steps.append(code)

        input_sha256 = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        job = DocumentJob(
            tenant_id=tenant_id,
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            pipeline_profile_id=payload.get("pipeline_profile_id"),
            preset_id=options.get("preset_id"),
            template_code=payload["template_code"],
            template_version=payload.get("template_version"),
            input_sha256=input_sha256,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id or str(uuid4()),
            created_by=created_by,
            input=payload,
        )
        self.session.add(job)
        await self.session.flush()

        for order, step in enumerate([*MANDATORY_STEPS, *optional_steps], start=1):
            self.session.add(
                DocumentJobStep(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    step_code=step,
                    order=order,
                    status=JobStepStatus.QUEUED.value,
                    max_attempts=RETRYABLE_STEPS.get(step, 0) + 1,
                    inputs_hash=input_sha256,
                    input_ref={"job_id": job.id, "step": step, "input_sha256": input_sha256},
                )
            )
        await self._log(job, "info", "job_created", None, {"correlation_id": job.correlation_id})
        await self.session.flush()
        return job

    async def run_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        if job.status == DocumentJobStatus.CANCELED.value:
            return job

        prev_status = job.status
        job.status = DocumentJobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(tz=timezone.utc)
        await self._audit_status_change(job, prev_status, job.status)
        await self.session.flush()
        await self.advance_job(job_id=job_id, fail_step=fail_step)
        return job

    async def advance_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")

        while True:
            if job.status == DocumentJobStatus.CANCELED.value or job.cancel_requested_at:
                await self._cancel_queued_steps(job)
                return job
            step = await self._next_queued_step(job.id)
            if step is None:
                break
            try:
                await self._run_step(job=job, step=step, fail_step=fail_step)
            except StepFailureError as exc:
                step.status = JobStepStatus.FAILED.value
                step.error_code = exc.code
                step.error_payload = exc.payload
                step.ended_at = datetime.now(tz=timezone.utc)
                prev_status = job.status
                job.status = DocumentJobStatus.FAILED.value
                job.error_code = exc.code
                job.error_payload = exc.payload
                job.ended_at = datetime.now(tz=timezone.utc)
                await self._audit_status_change(job, prev_status, job.status)
                await self._log(job, "error", "step_failed", step.step_code, {"error_code": exc.code, "error_payload": exc.payload})
                await self._audit_job_step(job=job, step=step, status=JobStepStatus.FAILED.value, started_at=step.started_at, ended_at=step.ended_at, error_code=exc.code, error_payload=exc.payload)
                await self._emit_event(job=job, event_type="Failed", payload={"job_id": job.id, "error_code": job.error_code, "correlation_id": job.correlation_id})
                await self.session.flush()
                return job

        prev_status = job.status
        job.status = DocumentJobStatus.SUCCESS.value
        job.ended_at = datetime.now(tz=timezone.utc)
        job.output = {"artifacts": await self._artifact_list(job.id)}
        await self._audit_status_change(job, prev_status, job.status)
        await self._emit_event(job=job, event_type="DocumentGenerated", payload={"job_id": job.id, "artifacts": await self._artifact_list(job.id), "correlation_id": job.correlation_id})
        await self._log(job, "info", "job_success", None, {"artifacts": len(job.output.get("artifacts", []))})
        await self.session.flush()
        return job

    async def cancel_job(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        if job.status in {DocumentJobStatus.SUCCESS.value, DocumentJobStatus.FAILED.value, DocumentJobStatus.CANCELED.value}:
            return job
        job.cancel_requested_at = datetime.now(tz=timezone.utc)
        job.status = DocumentJobStatus.CANCELED.value
        job.ended_at = datetime.now(tz=timezone.utc)
        await self._cancel_queued_steps(job)
        await self._log(job, "warning", "job_canceled", None, None)
        await self.session.flush()
        return job

    async def retry_job(self, *, job_id: str, retry_failed_only: bool = False) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        if job.status not in {DocumentJobStatus.FAILED.value, DocumentJobStatus.CANCELED.value}:
            raise ValueError("job_not_retryable")

        steps = (await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id).order_by(DocumentJobStep.order.asc()))).scalars().all()
        for step in steps:
            should_reset = step.status in {JobStepStatus.FAILED.value, JobStepStatus.CANCELED.value} if retry_failed_only else step.status != JobStepStatus.SUCCESS.value
            if should_reset:
                step.status = JobStepStatus.QUEUED.value
                step.error_code = None
                step.error_payload = None
                step.ended_at = None
                step.started_at = None

        job.status = DocumentJobStatus.QUEUED.value
        job.error_code = None
        job.error_payload = None
        job.ended_at = None
        job.cancel_requested_at = None
        await self._log(job, "info", "job_retry", None, {"retry_failed_only": retry_failed_only})
        await self.session.flush()
        return await self.run_job(job_id=job_id)

    async def retry_step(self, *, job_id: str, step_code: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        step = (await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id, DocumentJobStep.step_code == step_code))).scalar_one_or_none()
        if step is None:
            raise ValueError("step_not_found")
        if step.status not in {JobStepStatus.FAILED.value, JobStepStatus.CANCELED.value}:
            raise ValueError("step_not_retryable")

        step.status = JobStepStatus.QUEUED.value
        step.error_code = None
        step.error_payload = None
        step.ended_at = None
        step.started_at = None
        job.status = DocumentJobStatus.RUNNING.value
        job.error_code = None
        job.error_payload = None
        job.ended_at = None
        await self._log(job, "info", "step_rerun", step.step_code, None)
        await self.session.flush()
        return await self.advance_job(job_id=job_id)

    async def _next_queued_step(self, job_id: str) -> DocumentJobStep | None:
        return (await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id, DocumentJobStep.status == JobStepStatus.QUEUED.value).order_by(DocumentJobStep.order.asc()))).scalars().first()

    async def _run_step(self, *, job: DocumentJob, step: DocumentJobStep, fail_step: str | None) -> None:
        locked = await self.session.execute(
            update(DocumentJobStep)
            .where(DocumentJobStep.id == step.id, DocumentJobStep.status == JobStepStatus.QUEUED.value)
            .values(status=JobStepStatus.RUNNING.value, attempts=DocumentJobStep.attempts + 1, started_at=datetime.now(tz=timezone.utc))
        )
        if (locked.rowcount or 0) == 0:
            refreshed = await self.session.get(DocumentJobStep, step.id)
            if refreshed and refreshed.status == JobStepStatus.SUCCESS.value:
                return
            raise StepFailureError("step_lock_conflict", {"step": step.step_code}, retryable=True)
        await self.session.refresh(step)
        await self._log(job, "info", "step_started", step.step_code, {"attempt": step.attempts})
        await self._audit_job_step(job=job, step=step, status=JobStepStatus.RUNNING.value, started_at=step.started_at)

        if fail_step and step.step_code == fail_step:
            raise StepFailureError("step_failed", {"step": step.step_code, "attempt": step.attempts}, retryable=step.attempts < step.max_attempts)

        artifact_kind = self._artifact_kind(step.step_code)
        if artifact_kind and await self._artifact_exists(job.id, step.step_code, artifact_kind):
            step.status = JobStepStatus.SUCCESS.value
            step.ended_at = datetime.now(tz=timezone.utc)
            return

        if artifact_kind:
            self.session.add(
                DocumentArtifact(
                    tenant_id=job.tenant_id,
                    job_id=job.id,
                    step_code=step.step_code,
                    kind=artifact_kind,
                    sha256=(step.step_code.encode("utf-8").hex() + "0" * 64)[:64],
                    meta={"step": step.step_code, "correlation_id": job.correlation_id},
                )
            )
            step.output_ref = {"kind": artifact_kind, "step": step.step_code}

        step.status = JobStepStatus.SUCCESS.value
        step.error_code = None
        step.error_payload = None
        step.ended_at = datetime.now(tz=timezone.utc)
        await self._log(job, "info", "step_success", step.step_code, None)
        await self._audit_job_step(job=job, step=step, status=JobStepStatus.SUCCESS.value, started_at=step.started_at, ended_at=step.ended_at)

    async def _cancel_queued_steps(self, job: DocumentJob) -> None:
        steps = (await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id))).scalars().all()
        now = datetime.now(tz=timezone.utc)
        for step in steps:
            if step.status == JobStepStatus.QUEUED.value:
                step.status = JobStepStatus.CANCELED.value
                step.ended_at = now

    async def _emit_event(self, *, job: DocumentJob, event_type: str, payload: dict[str, Any]) -> None:
        dedup_source = f"{job.id}:{event_type}:{payload.get('correlation_id') or job.correlation_id}"
        dedup_event_id = hashlib.sha256(dedup_source.encode("utf-8")).hexdigest()[:36]
        self.session.add(
            OutboxEvent(
                tenant_id=job.tenant_id,
                event_type=event_type,
                event_id=dedup_event_id,
                payload={**payload, "tenant_id": job.tenant_id},
                status=OutboxEventStatus.PENDING.value,
                next_attempt_at=datetime.now(tz=timezone.utc),
            )
        )

    async def _log(self, job: DocumentJob, level: str, message: str, step_code: str | None, meta: dict[str, Any] | None) -> None:
        self.session.add(DocumentJobLog(tenant_id=job.tenant_id, job_id=job.id, step_code=step_code, level=level, message=message, meta_json={**(meta or {}), "correlation_id": job.correlation_id}))

    async def _audit_status_change(self, job: DocumentJob, before_status: str, after_status: str) -> None:
        if before_status == after_status:
            return
        await AuditService(self.session).log_event(
            tenant_id=job.tenant_id,
            action="status_change",
            object_type="DocumentJob",
            object_id=job.id,
            user_id=job.created_by,
            actor_type="service" if not job.created_by else "user",
            ip="system",
            request_id=job.correlation_id,
            changed_fields=field_level_diff({"status": before_status}, {"status": after_status}),
            details={"correlation_id": job.correlation_id},
        )


    async def _audit_job_step(
        self,
        *,
        job: DocumentJob,
        step: DocumentJobStep,
        status: str,
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        error_code: str | None = None,
        error_payload: dict[str, Any] | None = None,
    ) -> None:
        duration_ms: int | None = None
        if started_at and ended_at:
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)
        await AuditService(self.session).log_event(
            tenant_id=job.tenant_id,
            action="job_step",
            object_type="DocumentJob",
            object_id=job.id,
            user_id=job.created_by,
            actor_type="service" if not job.created_by else "user",
            ip="system",
            request_id=job.correlation_id,
            changed_fields={"fields": {"step_status": {"from": None, "to": status}}},
            details={
                "step_name": step.step_code,
                "attempt": step.attempts,
                "status": status,
                "duration_ms": duration_ms,
                "error_code": error_code,
                "error_payload_sanitized": error_payload,
                "resource_attrs": {"job_id": job.id},
                "correlation_id": job.correlation_id,
            },
        )

    @staticmethod
    def _artifact_kind(step_code: str) -> str | None:
        return {"render_docx": "docx", "convert_pdf": "pdf", "build_zip": "zip"}.get(step_code)

    async def _artifact_exists(self, job_id: str, step_code: str, kind: str) -> bool:
        return (await self.session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job_id, DocumentArtifact.step_code == step_code, DocumentArtifact.kind == kind))).scalar_one_or_none() is not None

    async def _artifact_list(self, job_id: str) -> list[dict[str, Any]]:
        artifacts = (await self.session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job_id))).scalars().all()
        return [{"step_code": a.step_code, "kind": a.kind, "sha256": a.sha256} for a in artifacts]
