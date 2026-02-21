from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.models import PipelineRun, PipelineRunStatus, Tenant, TenantCounter, TenantQuota


def _raise_quota(kind: str, *, limit: int, used: int, billing_gate: bool) -> None:
    code = status.HTTP_402_PAYMENT_REQUIRED if billing_gate else status.HTTP_429_TOO_MANY_REQUESTS
    error = "payment_required" if billing_gate else "quota_exceeded"
    raise HTTPException(
        code,
        detail={"code": error, "type": "tenancy", "message": f"Quota exceeded for {kind}", "meta": {"kind": kind, "limit": limit, "used": used}},
    )


async def check_concurrent_jobs(session: AsyncSession, *, tenant: Tenant, quota: TenantQuota) -> None:
    running_jobs = await session.scalar(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.tenant_id == tenant.slug,
            PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
        )
    )
    used = int(running_jobs or 0)
    limit = int(quota.max_parallel_jobs)
    if used + 1 > limit:
        _raise_quota("max_concurrent_jobs", limit=limit, used=used, billing_gate=bool(quota.enforce_billing_gate))


async def check_monthly_counters(session: AsyncSession, *, tenant: Tenant, quota: TenantQuota, delta: int = 1) -> None:
    period = datetime.now(timezone.utc).strftime("%Y%m")
    counter = (
        await session.execute(
            select(TenantCounter).where(TenantCounter.tenant_id == tenant.id, TenantCounter.yyyymm == period)
        )
    ).scalar_one_or_none()
    used = counter.doc_generations if counter else 0
    limit = int(quota.max_doc_generations_per_month)
    if used + delta > limit:
        _raise_quota("monthly_generations", limit=limit, used=used, billing_gate=bool(quota.enforce_billing_gate))
    if counter is None:
        counter = TenantCounter(tenant_id=tenant.id, yyyymm=period, doc_generations=0)
        session.add(counter)
    counter.doc_generations += delta


async def check_storage(session: AsyncSession, *, tenant: Tenant, quota: TenantQuota, delta: int = 0) -> None:
    used = await session.scalar(select(func.coalesce(func.sum(File.size), 0)).where(File.tenant_id == tenant.id))
    used = int(used or 0)
    limit = int(quota.max_storage_mb) * 1024 * 1024
    if used + delta > limit:
        _raise_quota("max_storage_mb", limit=limit, used=used, billing_gate=bool(quota.enforce_billing_gate))


async def assert_quota(session: AsyncSession, *, tenant: Tenant, kind: str, delta: int = 1) -> None:
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    if quota is None:
        return
    if kind == "jobs":
        await check_concurrent_jobs(session, tenant=tenant, quota=quota)
    elif kind == "generations_month":
        await check_monthly_counters(session, tenant=tenant, quota=quota, delta=delta)
    elif kind == "storage_bytes":
        await check_storage(session, tenant=tenant, quota=quota, delta=delta)
