from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Tenant,
    TenantCounter,
    TenantQuota,
    TenantQuotaCounter,
)


def _raise_quota(kind: str, *, limit: int, used: int, billing_gate: bool, correlation_id: str | None = None) -> None:
    code = status.HTTP_402_PAYMENT_REQUIRED if billing_gate else status.HTTP_429_TOO_MANY_REQUESTS
    error = "QUOTA_EXCEEDED"
    raise HTTPException(
        code,
        detail={"code": error, "type": "quota", "message": "Tenant quota exceeded", "correlation_id": correlation_id, "meta": {"kind": kind, "limit": limit, "used": used}},
    )


async def check_concurrent_jobs(session: AsyncSession, *, tenant: Tenant, quota: TenantQuota) -> None:
    tenant_scope = (str(tenant.id), tenant.slug)
    running_jobs = await session.scalar(
        select(func.count()).select_from(PipelineRun).where(
            PipelineRun.tenant_id.in_(tenant_scope),
            PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
        )
    )
    used = int(running_jobs or 0)
    limit = int(quota.max_parallel_jobs)
    if used + 1 > limit:
        _raise_quota("max_concurrent_jobs", limit=limit, used=used, billing_gate=bool(quota.enforce_billing_gate))


async def check_monthly_counters(session: AsyncSession, *, tenant: Tenant, quota: TenantQuota, delta: int = 1) -> None:
    period_counter = datetime.now(timezone.utc).strftime("%Y%m")
    period_quota = f"{period_counter[:4]}-{period_counter[4:]}"
    counter = (
        await session.execute(
            select(TenantCounter).where(TenantCounter.tenant_id == tenant.id, TenantCounter.yyyymm == period_counter)
        )
    ).scalar_one_or_none()
    used = counter.doc_generations if counter else 0
    limit = int(quota.max_doc_generations_per_month)
    if used + delta > limit:
        _raise_quota("generations_per_month", limit=limit, used=used, billing_gate=bool(quota.enforce_billing_gate))

    if counter is None:
        counter = TenantCounter(tenant_id=tenant.id, yyyymm=period_counter, doc_generations=0)
        session.add(counter)
    counter.doc_generations += delta

    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = insert(TenantQuotaCounter).values(
            tenant_id=tenant.id,
            counter_name="generations_per_month",
            period=period_quota,
            value=delta,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tenant_quota_counter",
            set_={"value": TenantQuotaCounter.value + delta},
        )
        await session.execute(stmt)
    else:
        quota_counter = (
            await session.execute(
                select(TenantQuotaCounter).where(
                    TenantQuotaCounter.tenant_id == tenant.id,
                    TenantQuotaCounter.counter_name == "generations_per_month",
                    TenantQuotaCounter.period == period_quota,
                )
            )
        ).scalar_one_or_none()
        if quota_counter is None:
            quota_counter = TenantQuotaCounter(
                tenant_id=tenant.id,
                counter_name="generations_per_month",
                period=period_quota,
                value=0,
            )
            session.add(quota_counter)
        quota_counter.value += delta


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
