from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.tenant_row_guard import assert_tenant_row_matches_session
from app.models.job_engine import DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus
from app.modules.pipelines.models import PipelineProfile
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator


class TenantSemaphore:
    def __init__(self, redis: Redis, tenant_id: str, max_parallel: int) -> None:
        self.redis = redis
        self.tenant_id = tenant_id
        self.max_parallel = max_parallel
        self.key = f"tenant:{tenant_id}:semaphore:jobs"

    async def acquire(self) -> bool:
        value = await self.redis.incr(self.key)
        if value > self.max_parallel:
            await self.redis.decr(self.key)
            return False
        await self.redis.expire(self.key, 900)
        return True

    async def release(self) -> None:
        await self.redis.decr(self.key)


class PipelineEngine:
    def __init__(self, session: AsyncSession, redis: Redis | None = None) -> None:
        self.session = session
        self.redis = redis
        self.delegate = DocumentPipelineOrchestrator(session)

    @asynccontextmanager
    async def tenant_slot(self, *, tenant_id: str, max_parallel: int):
        if self.redis is None:
            yield
            return
        semaphore = TenantSemaphore(self.redis, tenant_id, max_parallel)
        ok = await semaphore.acquire()
        if not ok:
            raise ValueError("tenant_parallel_limit_reached")
        try:
            yield
        finally:
            await semaphore.release()

    async def run_pipeline(self, *, job_id: str, profile: PipelineProfile) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines.engine.run_pipeline.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        limits = profile.limits or {}
        max_parallel = int(limits.get("max_parallel") or 1)
        async with self.tenant_slot(tenant_id=str(job.tenant_id), max_parallel=max_parallel):
            return await self.delegate.run_job(job_id=job_id)

    async def restart(self, *, job_id: str, restart_from_order: int) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines.engine.restart.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        steps = (
            await self.session.execute(
                select(DocumentJobStep).where(DocumentJobStep.job_id == job_id).order_by(DocumentJobStep.order.asc())
            )
        ).scalars().all()
        for step in steps:
            if step.order < restart_from_order:
                continue
            step.status = JobStepStatus.QUEUED.value
            step.error_code = None
            step.error_payload = None
            step.started_at = None
            step.ended_at = None
        job.status = DocumentJobStatus.QUEUED.value
        job.started_at = None
        job.ended_at = None
        job.attempts += 1
        await self.session.flush()
        return job

    async def cancel(self, *, job_id: str) -> DocumentJob:
        job = await self.session.get(DocumentJob, job_id)
        if job is None:
            raise ValueError("job_not_found")
        assert_tenant_row_matches_session(
            self.session,
            job,
            mismatch_event="pipelines.engine.cancel.tenant_scope_mismatch",
            not_found_message="job_not_found",
        )
        job.status = DocumentJobStatus.CANCELED.value
        job.ended_at = datetime.now(timezone.utc)
        steps = (
            await self.session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job_id))
        ).scalars().all()
        for step in steps:
            if step.status in {JobStepStatus.QUEUED.value, JobStepStatus.RUNNING.value}:
                step.status = JobStepStatus.CANCELED.value
                step.ended_at = datetime.now(timezone.utc)
        await self.session.flush()
        return job
