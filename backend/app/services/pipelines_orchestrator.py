from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_engine import DocumentArtifact, DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus
from app.modules.pipelines.models import PipelinePackageProfile, PipelineProfile
from app.services.audit import AuditService, field_level_diff
from app.services.file_storage import FileStorageService

DEFAULT_STEPS = ["render_docx", "apply_headers", "replace_apply", "convert_pdf", "build_zip", "archive"]
STUB_STEPS = {"sign", "edo", "index_file_content"}
RETRYABLE = {"convert_pdf": 2, "send_edo": 2, "edo": 2}


class PipelineOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.storage = FileStorageService.default()

    async def create_job(
        self,
        *,
        tenant_id: str,
        profile_code: str,
        payload: dict[str, Any],
        idempotency_key: str | None,
        request_hash: str,
        created_by: str | None = None,
        correlation_id: str | None = None,
    ) -> DocumentJob:
        if idempotency_key:
            existing = (
                await self.session.execute(
                    select(DocumentJob).where(
                        DocumentJob.tenant_id == tenant_id,
                        DocumentJob.idempotency_key == idempotency_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                if existing.request_hash != request_hash:
                    raise ValueError("idempotency_conflict")
                return existing

        profile = await self._resolve_profile(tenant_id=tenant_id, profile_code=profile_code)
        input_sha256 = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        job = DocumentJob(
            tenant_id=tenant_id,
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            profile_id=getattr(profile, "id", None),
            pipeline_profile_id=getattr(profile, "id", None),
            template_code=profile_code,
            input_sha256=input_sha256,
            request_hash=request_hash,
            idempotency_key=idempotency_key or f"job-{uuid4()}",
            correlation_id=correlation_id or str(uuid4()),
            created_by=created_by,
            input=payload,
            input_payload_json=payload,
        )
        self.session.add(job)
        await self.session.flush()

        steps = self._profile_steps(profile)
        for idx, step_key in enumerate(steps, start=1):
            self.session.add(
                DocumentJobStep(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    step_code=step_key,
                    step_key=step_key,
                    order=idx,
                    step_order=idx,
                    status=JobStepStatus.QUEUED.value,
                    max_attempts=RETRYABLE.get(step_key, 1),
                    input={"payload": payload},
                )
            )
        await self._audit_action(job=job, action="create_job", details={"profile_code": profile_code})
        await self.session.flush()
        return job

    async def start_job(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        prev = str(job.status)
        job.status = DocumentJobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(timezone.utc)
        await self._audit_diff(job, {"status": prev}, {"status": job.status})
        await self._audit_action(job=job, action="start_job", details={})
        await self.session.flush()
        return job

    async def continue_job(self, *, job_id: str, from_step_order: int | None = None) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        step = await self._next_step(job_id, from_step_order)
        if not step:
            if await self._all_done(job_id):
                job.status = DocumentJobStatus.SUCCESS.value
                job.ended_at = datetime.now(timezone.utc)
            await self.session.flush()
            return job
        job.current_step_index = step.step_order or step.order
        await self.session.flush()
        return job

    async def cancel_job(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        job.status = DocumentJobStatus.CANCELED.value
        job.ended_at = datetime.now(timezone.utc)
        for step in (
            await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id))
        ).scalars().all():
            if str(step.status) == JobStepStatus.QUEUED.value:
                step.status = JobStepStatus.CANCELED.value
                step.ended_at = datetime.now(timezone.utc)
        await self._audit_action(job=job, action="cancel_job", details={})
        await self.session.flush()
        return job

    async def retry_job(self, *, job_id: str, step_id: str | None = None, from_step_key: str | None = None, retry_failed_only: bool = False) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        steps = (
            await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id).order_by(DocumentJobStep.order.asc()))
        ).scalars().all()
        pivot_order = None
        if step_id:
            match = next((s for s in steps if s.id == step_id), None)
            if not match:
                raise ValueError("step_not_found")
            pivot_order = match.step_order or match.order
        elif from_step_key:
            match = next((s for s in steps if (s.step_key or s.step_code) == from_step_key), None)
            if not match:
                raise ValueError("step_not_found")
            pivot_order = match.step_order or match.order
        else:
            failed = next((s for s in steps if str(s.status) == JobStepStatus.FAILED.value), None)
            pivot_order = (failed.step_order or failed.order) if failed else 1

        for step in steps:
            if (step.step_order or step.order) >= pivot_order:
                step.status = JobStepStatus.QUEUED.value
                step.started_at = None
                step.ended_at = None
                step.error_code = None
                step.error_payload = None
                if (step.step_order or step.order) == pivot_order:
                    step.attempts += 1

        job.status = DocumentJobStatus.QUEUED.value
        job.error_code = None
        job.error_payload = None
        job.ended_at = None
        await self._audit_action(job=job, action="retry_job", details={"pivot_order": pivot_order})
        await self.session.flush()
        return job

    async def run_step(self, *, job_id: str, step_id: str) -> DocumentJobStep:
        step = await self.session.get(DocumentJobStep, step_id)
        if not step or step.job_id != job_id:
            raise ValueError("step_not_found")
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")

        locked = await self.session.execute(
            update(DocumentJobStep)
            .where(DocumentJobStep.id == step_id, DocumentJobStep.status.in_([JobStepStatus.QUEUED.value, JobStepStatus.FAILED.value]))
            .values(status=JobStepStatus.RUNNING.value, started_at=datetime.now(timezone.utc))
        )
        if not (locked.rowcount or 0):
            return step
        await self.session.refresh(step)
        await self._write_step_log(job, step, "info", "step_started", {"attempt": step.attempts})

        handler = self._dispatch(step.step_key or step.step_code)
        try:
            out = handler(job=job, step=step)
            step.output = out
            step.output_ref = out
            step.status = JobStepStatus.SUCCESS.value
            step.ended_at = datetime.now(timezone.utc)
            if step.step_key == "archive":
                job.output_payload_json = {"artifacts": await self._artifact_list(job.id)}
                job.output = job.output_payload_json
            await self._write_step_log(job, step, "info", "step_success", out)
            await self._audit_step(job, step)
        except Exception as exc:  # noqa: BLE001
            step.status = JobStepStatus.FAILED.value
            step.error_code = "step_failed"
            step.error_payload = {"message": str(exc)}
            step.ended_at = datetime.now(timezone.utc)
            await self._write_step_log(job, step, "error", "step_failed", step.error_payload)
            if step.attempts >= step.max_attempts:
                job.status = DocumentJobStatus.FAILED.value
                job.error_code = step.error_code
                job.error_payload = step.error_payload
                job.ended_at = datetime.now(timezone.utc)
            raise
        finally:
            await self.session.flush()
        return step

    async def _next_step(self, job_id: str, from_step_order: int | None = None) -> DocumentJobStep | None:
        stmt = select(DocumentJobStep).where(DocumentJobStep.job_id == job_id, DocumentJobStep.status == JobStepStatus.QUEUED.value)
        if from_step_order is not None:
            stmt = stmt.where(DocumentJobStep.order >= from_step_order)
        return (await self.session.execute(stmt.order_by(DocumentJobStep.order.asc()))).scalars().first()

    async def _all_done(self, job_id: str) -> bool:
        steps = (await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id))).scalars().all()
        return all(str(s.status) in {JobStepStatus.SUCCESS.value, JobStepStatus.SKIPPED.value} for s in steps)

    async def _resolve_profile(self, *, tenant_id: str, profile_code: str) -> PipelineProfile | PipelinePackageProfile:
        profile = (
            await self.session.execute(
                select(PipelineProfile).where(PipelineProfile.tenant_id == tenant_id, PipelineProfile.code == profile_code, PipelineProfile.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if profile:
            return profile
        package = (
            await self.session.execute(
                select(PipelinePackageProfile).where(PipelinePackageProfile.tenant_id == tenant_id, PipelinePackageProfile.code == profile_code)
            )
        ).scalar_one_or_none()
        if package:
            return package
        raise ValueError("profile_not_found")

    @staticmethod
    def _profile_steps(profile: PipelineProfile | PipelinePackageProfile) -> list[str]:
        raw = getattr(profile, "steps", None) or getattr(profile, "steps_json", None) or []
        codes = [s.get("code") if isinstance(s, dict) else str(s) for s in raw]
        codes = [c for c in codes if c]
        return codes or DEFAULT_STEPS

    def _dispatch(self, step_key: str):
        def _artifact_handler(*, job: DocumentJob, step: DocumentJobStep) -> dict[str, Any]:
            key = f"{job.tenant_id}/jobs/{job.id}/{step_key}.bin"
            self.storage.put(key, f"{step_key}:{job.id}".encode("utf-8"), content_type="application/octet-stream")
            self.session.add(DocumentArtifact(tenant_id=job.tenant_id, job_id=job.id, step_code=step_key, kind=step_key, meta={"key": key}))
            return {"artifact_key": key, "kind": step_key}

        if step_key in {"render_docx", "apply_headers", "replace_apply", "convert_pdf", "build_zip", "archive"}:
            return _artifact_handler
        if step_key in STUB_STEPS:
            return lambda *, job, step: {"stub": True, "step": step_key}
        return lambda *, job, step: {"noop": True, "step": step_key}

    async def _write_step_log(self, job: DocumentJob, step: DocumentJobStep, level: str, message: str, meta: dict[str, Any] | None) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "meta": meta or {},
        }
        logs_uri = step.logs_uri or f"s3://{job.tenant_id}/jobs/{job.id}/{step.step_key or step.step_code}.jsonl"
        store_key = logs_uri.replace("s3://", "")
        current = b""
        if self.storage.has(store_key):
            current = self.storage.get(store_key)
        payload = current + (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        self.storage.put(store_key, payload, content_type="application/jsonl")
        step.logs_uri = logs_uri

    async def _artifact_list(self, job_id: str) -> list[dict[str, Any]]:
        rows = (await self.session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job_id))).scalars().all()
        return [{"step_code": r.step_code, "kind": r.kind, "meta": r.meta} for r in rows]

    async def _audit_diff(self, job: DocumentJob, before: dict[str, Any], after: dict[str, Any]) -> None:
        await AuditService(self.session).log_event(
            tenant_id=job.tenant_id,
            action="job_diff",
            object_type="DocumentJob",
            object_id=job.id,
            user_id=job.created_by,
            actor_type="service" if not job.created_by else "user",
            ip="system",
            request_id=job.correlation_id,
            changed_fields=field_level_diff(before, after),
            details={"correlation_id": job.correlation_id},
        )

    async def _audit_step(self, job: DocumentJob, step: DocumentJobStep) -> None:
        await AuditService(self.session).log_event(
            tenant_id=job.tenant_id,
            action="step_diff",
            object_type="DocumentJob",
            object_id=job.id,
            user_id=job.created_by,
            actor_type="service" if not job.created_by else "user",
            ip="system",
            request_id=job.correlation_id,
            changed_fields={
                "fields": {
                    "job.status": {"from": None, "to": job.status},
                    "job.current_step_index": {"from": None, "to": job.current_step_index},
                    "step.status": {"from": None, "to": step.status},
                    "step.attempt": {"from": None, "to": step.attempts},
                }
            },
            details={"step_key": step.step_key or step.step_code},
        )

    async def _audit_action(self, *, job: DocumentJob, action: str, details: dict[str, Any]) -> None:
        await AuditService(self.session).log_event(
            tenant_id=job.tenant_id,
            action=action,
            object_type="DocumentJob",
            object_id=job.id,
            user_id=job.created_by,
            actor_type="service" if not job.created_by else "user",
            ip="system",
            request_id=job.correlation_id,
            changed_fields=None,
            details=details,
        )


class DocumentPipelineOrchestrator(PipelineOrchestrator):
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
        return await self.create_job(
            tenant_id=tenant_id,
            profile_code=payload["template_code"],
            payload=payload,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            created_by=created_by,
            correlation_id=correlation_id,
        )

    async def run_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        job = await self.start_job(job_id=job_id)
        while True:
            step = await self._next_step(job.id)
            if not step:
                break
            if fail_step and (step.step_key or step.step_code) == fail_step:
                step.status = JobStepStatus.FAILED.value
                step.error_code = "step_failed"
                step.error_payload = {"forced": True}
                job.status = DocumentJobStatus.FAILED.value
                await self.session.flush()
                return job
            await self.run_step(job_id=job.id, step_id=step.id)
        await self.continue_job(job_id=job.id)
        return job

    async def advance_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        return await self.run_job(job_id=job_id, fail_step=fail_step)

    async def retry_step(self, *, job_id: str, step_code: str) -> DocumentJob:
        await self.retry_job(job_id=job_id, from_step_key=step_code)
        return await self.run_job(job_id=job_id)
