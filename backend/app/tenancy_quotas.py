from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.models import PipelineRun, PipelineRunStatus, Tenant, TenantCounter, TenantQuota


async def assert_quota(session: AsyncSession, *, tenant: Tenant, kind: str, delta: int = 1) -> None:
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    if quota is None:
        return

    if kind == "generations_month":
        period = datetime.now(timezone.utc).strftime("%Y%m")
        counter = (
            await session.execute(
                select(TenantCounter).where(TenantCounter.tenant_id == tenant.id, TenantCounter.yyyymm == period)
            )
        ).scalar_one_or_none()
        used = counter.doc_generations if counter else 0
        limit = quota.max_doc_generations_per_month
        if used + delta > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "quota_exceeded", "meta": {"kind": kind, "limit": limit, "used": used}})
        if counter is None:
            counter = TenantCounter(tenant_id=tenant.id, yyyymm=period, doc_generations=0)
            session.add(counter)
        counter.doc_generations += delta
        return

    if kind == "storage_bytes":
        used = await session.scalar(select(func.coalesce(func.sum(File.size), 0)).where(File.tenant_id == tenant.id))
        used = int(used or 0)
        limit = int(quota.max_storage_mb) * 1024 * 1024
        if used + delta > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "quota_exceeded", "meta": {"kind": kind, "limit": limit, "used": used}})
        return

    if kind == "jobs":
        running_jobs = await session.scalar(
            select(func.count()).select_from(PipelineRun).where(
                PipelineRun.tenant_id == tenant.slug,
                PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
            )
        )
        used = int(running_jobs or 0)
        limit = quota.max_parallel_jobs
        if used + delta > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "quota_exceeded", "meta": {"kind": kind, "limit": limit, "used": used}})
        return
