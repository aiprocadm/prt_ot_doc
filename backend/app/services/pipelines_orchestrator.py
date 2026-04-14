from __future__ import annotations

import hashlib
import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant_row_guard import assert_tenant_row_matches_session
from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
    OutboxEvent,
    OutboxEventStatus,
    PipelineStepLock,
)
from app.models.models import Tenant, TenantQuota
from app.modules.files.models import FileEntityType, FileLinkRole
from app.modules.files.service import FileService
from app.modules.pipelines.document_core_profile import DOCUMENT_CORE_PIPELINE_STEPS
from app.modules.pipelines.graph import safe_eval_condition
from app.modules.pipelines.models import PipelinePackageProfile, PipelineProfile
from app.services.audit import AuditService, field_level_diff
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService
from app.services.pipeline_step_handlers import (
    artifact_step_handler,
    edo_step_handler,
    index_projection_step_handler,
    quality_gate_step_handler,
    signature_step_handler,
    validate_template_step_handler,
)

DEFAULT_STEPS = list(DOCUMENT_CORE_PIPELINE_STEPS)
INTERNAL_PROJECTION_STEPS = {"send_for_approval", "sign", "verify_signature", "index_file_content"}
RETRYABLE = {"convert_pdf": 2, "send_edo": 2}
STEP_ALIASES = {
    "replace_apply": "replace",
    "edo": "send_edo",
}


def _sanitize_log_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_log_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_log_payload(v) for v in value]
    if isinstance(value, str):
        lowered = value.lower()
        if "@" in value and "." in value:
            return "***"
        if any(token in lowered for token in ("паспорт", "passport", "snils", "снилс")):
            return "***"
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) >= 10:
            return "***"
    return value


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
        enqueue: bool = True,
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
        input_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        job = DocumentJob(
            tenant_id=tenant_id,
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            queued_at=datetime.now(timezone.utc),
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
        for idx, step_def in enumerate(steps, start=1):
            step_key = STEP_ALIASES.get(step_def["kind"], step_def["kind"])
            self.session.add(
                DocumentJobStep(
                    tenant_id=tenant_id,
                    job_id=job.id,
                    step_code=step_def["node_id"],
                    step_key=step_key,
                    order=idx,
                    seq=idx,
                    step_order=idx,
                    status=JobStepStatus.QUEUED.value,
                    max_attempts=int(step_def.get("max_attempts") or RETRYABLE.get(step_key, 1)),
                    input={
                        "payload": payload,
                        "depends_on": step_def.get("depends_on", []),
                        "condition": step_def.get("condition"),
                        "config": step_def.get("config", {}),
                    },
                )
            )
        await self._audit_action(
            job=job, action="create_job", details={"profile_code": profile_code}
        )
        await self.session.flush()
        return job

    async def start_job(self, *, job_id: str, enqueue: bool = True) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines_orchestrator.start_job.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        prev = str(job.status)
        limit = await self._tenant_concurrency_limit(job)
        if limit is not None:
            slot_acquired = await self._try_acquire_tenant_slot(job, limit)
            if not slot_acquired:
                await self.session.flush()
                return job
        job.status = DocumentJobStatus.RUNNING.value
        job.started_at = job.started_at or datetime.now(timezone.utc)
        await self._audit_diff(job, {"status": prev}, {"status": job.status})
        await self._audit_action(job=job, action="start_job", details={})
        await self.session.flush()
        if enqueue:
            await self.continue_job(job_id=job.id)
        return job

    async def continue_job(
        self, *, job_id: str, from_step_order: int | None = None, enqueue: bool = True
    ) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines_orchestrator.continue_job.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        if str(job.status) == DocumentJobStatus.CANCELED.value:
            queued_steps = (
                (
                    await self.session.execute(
                        select(DocumentJobStep).where(
                            DocumentJobStep.job_id == job_id,
                            DocumentJobStep.status == JobStepStatus.QUEUED.value,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for queued in queued_steps:
                queued.status = JobStepStatus.CANCELED.value
                queued.ended_at = datetime.now(timezone.utc)
            await self.session.flush()
            return job
        step = await self._next_step(job_id, from_step_order)
        if not step:
            if await self._all_done(job_id):
                job.status = DocumentJobStatus.SUCCESS.value
                job.ended_at = datetime.now(timezone.utc)
                await self._release_tenant_slot(job)
                await self._ensure_document_generated_event(job)
            await self.session.flush()
            return job
        job.current_step_index = step.step_order or step.order
        if enqueue:
            await self.enqueue_next_step(job=job, step=step)
        await self.session.flush()
        return job

    async def cancel_job(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines_orchestrator.cancel_job.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        job.status = DocumentJobStatus.CANCELED.value
        job.ended_at = datetime.now(timezone.utc)
        await self._release_tenant_slot(job)
        for step in (
            (
                await self.session.execute(
                    select(DocumentJobStep).where(DocumentJobStep.job_id == job_id)
                )
            )
            .scalars()
            .all()
        ):
            if str(step.status) == JobStepStatus.QUEUED.value:
                step.status = JobStepStatus.CANCELED.value
                step.ended_at = datetime.now(timezone.utc)
        await self._audit_action(job=job, action="cancel_job", details={})
        await self.session.flush()
        return job

    async def retry_job(
        self,
        *,
        job_id: str,
        step_id: str | None = None,
        from_step_key: str | None = None,
        retry_failed_only: bool = False,
    ) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines_orchestrator.retry_job.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        steps = (
            (
                await self.session.execute(
                    select(DocumentJobStep)
                    .where(DocumentJobStep.job_id == job_id)
                    .order_by(DocumentJobStep.order.asc())
                )
            )
            .scalars()
            .all()
        )
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
            if retry_failed_only and str(step.status) != JobStepStatus.FAILED.value:
                continue
            if (step.step_order or step.order) >= pivot_order:
                step.status = JobStepStatus.QUEUED.value
                step.started_at = None
                step.ended_at = None
                step.error_code = None
                step.error_payload = None

        job.status = DocumentJobStatus.QUEUED.value
        job.error_code = None
        job.error_payload = None
        job.ended_at = None
        await self._audit_action(job=job, action="retry_job", details={"pivot_order": pivot_order})
        await self.session.flush()
        return job

    async def run_step(self, *, job_id: str, step_id: str) -> DocumentJobStep:
        step = await self.session.get(DocumentJobStep, step_id)
        if not step:
            raise ValueError("step_not_found")
        assert_tenant_row_matches_session(
            self.session,
            step,
            mismatch_event="pipelines_orchestrator.run_step.step_tenant_scope_mismatch",
            not_found_message="step_not_found",
        )
        if step.job_id != job_id:
            raise ValueError("step_not_found")
        job = await self.session.get(DocumentJob, job_id)
        if not job:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines_orchestrator.run_step.job_tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        if str(job.status) == DocumentJobStatus.CANCELED.value:
            if str(step.status) in {JobStepStatus.QUEUED.value, JobStepStatus.RUNNING.value}:
                step.status = JobStepStatus.CANCELED.value
                step.ended_at = datetime.now(timezone.utc)
                await self.session.flush()
            return step

        locked = await self.session.execute(
            update(DocumentJobStep)
            .where(
                DocumentJobStep.id == step_id,
                DocumentJobStep.status.in_(
                    [JobStepStatus.QUEUED.value, JobStepStatus.FAILED.value]
                ),
            )
            .values(
                status=JobStepStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc),
                attempts=DocumentJobStep.attempts + 1,
                attempt=DocumentJobStep.attempt + 1,
            )
        )
        if not (locked.rowcount or 0):
            return step
        await self.session.refresh(step)
        await self._write_step_log(job, step, "info", "step_started", {"attempt": step.attempts})

        handler = self._dispatch(step.step_key or step.step_code)
        try:
            out = handler(job=job, step=step)
            if inspect.isawaitable(out):
                out = await out
            step.output = out
            step.output_ref = out
            step.status = JobStepStatus.SUCCESS.value
            step.logs_ref = step.logs_uri or step.logs_ref
            step.ended_at = datetime.now(timezone.utc)
            if step.step_key == "archive":
                job.output_payload_json = {"artifacts": await self._artifact_list(job.id)}
                job.output = job.output_payload_json
            await self._write_step_log(job, step, "info", "step_success", out)
            await self._audit_step(job, step)
        except Exception as exc:  # noqa: BLE001
            step.error_code = "step_failed"
            step.error_payload = {"message": str(exc)}
            step.ended_at = datetime.now(timezone.utc)
            if step.attempt < step.max_attempts:
                step.status = JobStepStatus.QUEUED.value
                step.started_at = None
                step.ended_at = None
                await self._write_step_log(
                    job,
                    step,
                    "warning",
                    "step_retry_scheduled",
                    {"attempt": step.attempt, "max_attempts": step.max_attempts},
                )
            else:
                step.status = JobStepStatus.FAILED.value
                await self._write_step_log(job, step, "error", "step_failed", step.error_payload)
                job.status = DocumentJobStatus.FAILED.value
                job.error_code = step.error_code
                job.error_payload = step.error_payload
                job.ended_at = datetime.now(timezone.utc)
                await self._release_tenant_slot(job)
            if step.status == JobStepStatus.FAILED.value:
                raise
        finally:
            await self.session.flush()
        return step

    async def enqueue_next_step(self, *, job: DocumentJob, step: DocumentJobStep) -> None:
        from app.celery.tasks.job_steps import run_job_step

        if celery_app.conf.task_always_eager:
            await self.session.commit()

        tenant_slug = await self._resolve_job_tenant_slug(str(job.tenant_id))

        run_job_step.apply_async(
            kwargs={
                "tenant_slug": tenant_slug,
                "tenant_id": str(job.tenant_id),
                "job_id": job.id,
                "step_id": step.id,
            },
            headers={"tenant_id": str(job.tenant_id)},
        )

    async def _resolve_job_tenant_slug(self, tenant_id: str) -> str:
        session_info = getattr(self.session, "info", None)
        if isinstance(session_info, dict):
            session_tenant_id = str(session_info.get("tenant_id") or "").strip() or None
            session_tenant_slug = (
                str(session_info.get("tenant_slug") or session_info.get("tenant") or "").strip().lower() or None
            )
            if session_tenant_id == tenant_id and session_tenant_slug:
                return session_tenant_slug

        tenant_slug = (
            await self.session.execute(
                select(Tenant.slug).where(Tenant.id == tenant_id).limit(1)
            )
        ).scalar_one_or_none()
        if tenant_slug:
            return str(tenant_slug).strip().lower()
        raise ValueError(f"Tenant slug not found for tenant_id {tenant_id}")

    async def _next_step(
        self, job_id: str, from_step_order: int | None = None
    ) -> DocumentJobStep | None:
        stmt = select(DocumentJobStep).where(
            DocumentJobStep.job_id == job_id, DocumentJobStep.status == JobStepStatus.QUEUED.value
        )
        if from_step_order is not None:
            stmt = stmt.where(DocumentJobStep.order >= from_step_order)
        candidates = (
            (await self.session.execute(stmt.order_by(DocumentJobStep.order.asc()))).scalars().all()
        )
        status_by_node = {
            s.step_code: str(s.status)
            for s in (
                await self.session.execute(
                    select(DocumentJobStep).where(DocumentJobStep.job_id == job_id)
                )
            )
            .scalars()
            .all()
        }
        for step in candidates:
            meta = step.input or {}
            deps = meta.get("depends_on", [])
            if any(
                status_by_node.get(dep)
                not in {JobStepStatus.SUCCESS.value, JobStepStatus.SKIPPED.value}
                for dep in deps
            ):
                continue
            condition = meta.get("condition")
            if condition:
                payload = meta.get("payload", {}) if isinstance(meta, dict) else {}
                input_meta = payload.get("input", {}) if isinstance(payload, dict) else {}
                ctx = {"artifacts": {}, "meta": {"job_id": job_id, **input_meta}}
                if not safe_eval_condition(condition, ctx):
                    step.status = JobStepStatus.SKIPPED.value
                    step.ended_at = datetime.now(timezone.utc)
                    continue
            return step
        return None

    async def _all_done(self, job_id: str) -> bool:
        steps = (
            (
                await self.session.execute(
                    select(DocumentJobStep).where(DocumentJobStep.job_id == job_id)
                )
            )
            .scalars()
            .all()
        )
        return all(
            str(s.status) in {JobStepStatus.SUCCESS.value, JobStepStatus.SKIPPED.value}
            for s in steps
        )

    async def _try_acquire_tenant_slot(self, job: DocumentJob, limit: int) -> bool:
        lock = (
            await self.session.execute(
                select(PipelineStepLock).where(PipelineStepLock.tenant_id == job.tenant_id)
            )
        ).scalar_one_or_none()
        if lock is None:
            lock = PipelineStepLock(tenant_id=job.tenant_id, running_count=0)
            self.session.add(lock)
            await self.session.flush()
        if lock.running_count >= limit:
            return False
        lock.running_count += 1
        return True

    async def _release_tenant_slot(self, job: DocumentJob) -> None:
        lock = (
            await self.session.execute(
                select(PipelineStepLock).where(PipelineStepLock.tenant_id == job.tenant_id)
            )
        ).scalar_one_or_none()
        if lock is None:
            return
        lock.running_count = max(0, int(lock.running_count or 0) - 1)

    async def _tenant_concurrency_limit(self, job: DocumentJob) -> int | None:
        try:
            quota = (
                await self.session.execute(
                    select(TenantQuota.max_parallel_jobs).where(TenantQuota.tenant_id == job.tenant_id)
                )
            ).scalar_one_or_none()
        except SQLAlchemyError:
            quota = None
        if quota is not None:
            try:
                return max(1, int(quota))
            except (TypeError, ValueError):
                return 1
        profile_id = job.profile_id or job.pipeline_profile_id
        if not profile_id:
            return None
        profile = await self.session.get(PipelineProfile, profile_id)
        if profile is None:
            return None
        try:
            assert_tenant_row_matches_session(
                self.session,
                profile,
                mismatch_event="pipelines_orchestrator.tenant_concurrency_limit.profile_tenant_scope_mismatch",
                not_found_message="job_not_found",
            )
        except ValueError:
            return None
        if str(profile.tenant_id) != str(job.tenant_id):
            return None
        if getattr(profile, "concurrency_limit_per_tenant", None) is not None:
            try:
                return int(profile.concurrency_limit_per_tenant)
            except (TypeError, ValueError):
                return None
        limits = profile.limits or {}
        raw = limits.get("concurrency_limit_per_tenant") if isinstance(limits, dict) else None
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    async def _resolve_profile(
        self, *, tenant_id: str, profile_code: str
    ) -> PipelineProfile | PipelinePackageProfile | SimpleNamespace:
        profile = (
            await self.session.execute(
                select(PipelineProfile).where(
                    PipelineProfile.tenant_id == tenant_id,
                    PipelineProfile.code == profile_code,
                    PipelineProfile.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if profile:
            return profile
        package = (
            await self.session.execute(
                select(PipelinePackageProfile).where(
                    PipelinePackageProfile.tenant_id == tenant_id,
                    PipelinePackageProfile.code == profile_code,
                )
            )
        ).scalar_one_or_none()
        if package:
            return package
        return SimpleNamespace(
            id=None,
            code=profile_code,
            steps_json=[{"code": step} for step in DEFAULT_STEPS],
        )

    @staticmethod
    def _profile_steps(
        profile: PipelineProfile | PipelinePackageProfile | SimpleNamespace,
    ) -> list[dict[str, Any]]:
        graph = getattr(profile, "graph", None) or {}
        nodes = graph.get("nodes") or []
        edges = graph.get("edges") or []
        if nodes:
            incoming: dict[str, list[dict[str, Any]]] = {
                n.get("id"): [] for n in nodes if n.get("id")
            }
            for edge in edges:
                to_node = edge.get("to")
                if to_node in incoming:
                    incoming[to_node].append(edge)
            ordered = sorted(nodes, key=lambda n: n.get("id", ""))
            return [
                {
                    "node_id": node["id"],
                    "kind": node.get("type", "noop"),
                    "depends_on": [
                        e.get("from") for e in incoming.get(node["id"], []) if e.get("from")
                    ],
                    "condition": next(
                        (
                            e.get("condition")
                            for e in incoming.get(node["id"], [])
                            if e.get("condition")
                        ),
                        None,
                    ),
                    "max_attempts": ((node.get("retry") or {}).get("max_attempts")),
                    "config": node.get("config", {}),
                }
                for node in ordered
            ]
        raw = getattr(profile, "steps", None) or getattr(profile, "steps_json", None) or []
        parsed: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                if item.get("enabled") is False:
                    continue
                code = item.get("code") or item.get("kind")
                if not code:
                    continue
                retry_policy = item.get("retry_policy") or {}
                parsed.append(
                    {
                        "node_id": code,
                        "kind": code,
                        "depends_on": [],
                        "condition": None,
                        "config": item.get("config", {}),
                        "max_attempts": item.get("max_attempts")
                        or retry_policy.get("max_attempts"),
                        "timeout_s": item.get("timeout_s"),
                    }
                )
            else:
                code = str(item)
                if code:
                    parsed.append(
                        {
                            "node_id": code,
                            "kind": code,
                            "depends_on": [],
                            "condition": None,
                            "config": {},
                        }
                    )
        return parsed or [
            {"node_id": c, "kind": c, "depends_on": [], "condition": None, "config": {}}
            for c in DEFAULT_STEPS
        ]

    def _dispatch(self, step_key: str):
        if step_key == "validate_template":
            return lambda *, job, step: validate_template_step_handler(
                session=self.session, job=job, step=step
            )
        if step_key in {
            "render_docx",
            "apply_headers",
            "replace",
            "convert_pdf",
            "build_zip",
            "archive",
        }:
            return lambda *, job, step: artifact_step_handler(
                session=self.session, job=job, step=step, step_key=step_key
            )
        if step_key == "send_edo":
            return edo_step_handler
        if step_key == "quality_gate":
            return quality_gate_step_handler
        if step_key in {"sign", "verify_signature"}:
            return lambda *, job, step: signature_step_handler(job=job, step=step, step_key=step_key)
        if step_key == "index_file_content":
            return index_projection_step_handler
        if step_key in INTERNAL_PROJECTION_STEPS:
            return lambda *, job, step: {"status": "completed", "step": step_key}
        return lambda *, job, step: {"noop": True, "step": step_key}

    async def _write_step_log(
        self,
        job: DocumentJob,
        step: DocumentJobStep,
        level: str,
        message: str,
        meta: dict[str, Any] | None,
    ) -> None:
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "meta": _sanitize_log_payload(meta or {}),
        }
        store_key = f"logs/jobs/{job.id}/{step.step_key or step.step_code}.jsonl"
        current = b""
        if self.storage.has(store_key):
            current = self.storage.get(store_key)
        payload = current + (json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8")
        self.storage.put(store_key, payload, content_type="application/jsonl")
        svc = FileService(session=self.session, tenant_id=str(job.tenant_id))
        file_record = await svc.create_artifact_from_bytes(
            payload=payload,
            filename=f"{step.step_key or step.step_code}.jsonl",
            content_type="application/jsonl",
            job_id=job.id,
            step_key=step.step_key or step.step_code,
            metadata_json={
                "job_id": job.id,
                "step_key": step.step_key or step.step_code,
                "log": True,
            },
            entity_type=FileEntityType.job_step.value,
            entity_id=step.id,
            role=FileLinkRole.log.value,
        )
        step.logs_file_id = file_record.id
        step.logs_uri = None
        step.logs_ref = f"s3://{store_key}"

    async def _artifact_list(self, job_id: str) -> list[dict[str, Any]]:
        rows = (
            (
                await self.session.execute(
                    select(DocumentArtifact).where(DocumentArtifact.job_id == job_id)
                )
            )
            .scalars()
            .all()
        )
        return [{"step_code": r.step_code, "kind": r.kind, "meta": r.meta} for r in rows]

    async def _ensure_document_generated_event(self, job: DocumentJob) -> None:
        existing = (
            await self.session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.tenant_id == job.tenant_id, OutboxEvent.event_id == job.id
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return
        self.session.add(
            OutboxEvent(
                tenant_id=job.tenant_id,
                event_type="DocumentGenerated",
                aggregate_type="document_job",
                aggregate_id=job.id,
                event_id=job.id,
                payload={
                    "job_id": job.id,
                    "status": job.status,
                    "artifacts": await self._artifact_list(job.id),
                    "tenant_id": job.tenant_id,
                    "correlation_id": job.correlation_id,
                },
                headers={
                    "correlation_id": job.correlation_id,
                    "produced_by": "pipelines_orchestrator",
                    "schema_version": "1",
                },
                status=OutboxEventStatus.PENDING.value,
                next_attempt_at=datetime.now(timezone.utc),
            )
        )

    async def _audit_diff(
        self, job: DocumentJob, before: dict[str, Any], after: dict[str, Any]
    ) -> None:
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
                    "step.attempt": {"from": None, "to": step.attempt},
                }
            },
            details={"step_key": step.step_key or step.step_code},
        )

    async def _audit_action(
        self, *, job: DocumentJob, action: str, details: dict[str, Any]
    ) -> None:
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
        enqueue: bool = True,
    ) -> DocumentJob:
        job = await self.create_job(
            tenant_id=tenant_id,
            profile_code=payload["template_code"],
            payload=payload,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            created_by=created_by,
            correlation_id=correlation_id,
        )
        return await self.start_job(job_id=job.id, enqueue=enqueue)

    async def run_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        job = await self.start_job(job_id=job_id, enqueue=False)
        while True:
            step = await self._next_step(job.id)
            if not step:
                break
            if fail_step and (step.step_key or step.step_code) == fail_step:
                step.status = JobStepStatus.FAILED.value
                step.error_code = "step_failed"
                step.error_payload = {"forced": True}
                job.status = DocumentJobStatus.FAILED.value
                job.error_code = step.error_code
                job.error_payload = step.error_payload
                job.ended_at = datetime.now(timezone.utc)
                await self._release_tenant_slot(job)
                await self.session.flush()
                return job
            await self.run_step(job_id=job.id, step_id=step.id)
        await self.continue_job(job_id=job.id, enqueue=False)
        return job

    async def advance_job(self, *, job_id: str, fail_step: str | None = None) -> DocumentJob:
        return await self.run_job(job_id=job_id, fail_step=fail_step)

    async def retry_step(self, *, job_id: str, step_code: str) -> DocumentJob:
        await self.retry_job(job_id=job_id, from_step_key=step_code)
        return await self.run_job(job_id=job_id)
