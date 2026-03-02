from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.models import BillingPlan, BillingSubscription, BillingSubscriptionStatus, BillingUsageCounter, Tenant
from app.services.billing import BillingContext, BillingService


@pytest.mark.asyncio
async def test_compute_remaining_uses_usage_counters() -> None:
    usage = BillingUsageCounter(tenant_id="t1", period_yyyymm=202603, docs_generated=12, edo_outgoing=4, s3_bytes_used=3 * 1024**3)
    remaining = BillingService.compute_remaining(
        {"max_generations_per_month": 20, "edo_outgoing_per_month": 5, "max_s3_bytes": 10 * 1024**3}, usage
    )
    assert remaining["max_generations_per_month"] == 8
    assert remaining["edo_outgoing_per_month"] == 1
    assert remaining["max_s3_bytes"] == 7 * 1024**3


@pytest.mark.asyncio
async def test_assert_allowed_blocks_past_due_without_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    service = BillingService(session=None)  # type: ignore[arg-type]
    tenant = Tenant(id="tenant-1", slug="tenant-1", name="Tenant 1", code="tenant-1", schema_name="tenant_1")
    subscription = BillingSubscription(
        tenant_id=tenant.id,
        plan_id="plan-1",
        status=BillingSubscriptionStatus.PAST_DUE,
        period_start=datetime.now(tz=timezone.utc) - timedelta(days=30),
        period_end=datetime.now(tz=timezone.utc),
        auto_renew=True,
        grace_until=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
    )
    context = BillingContext(plan=None, subscription=subscription, usage=None, limits={}, features={})

    async def _get_context(_: Tenant) -> BillingContext:
        return context

    monkeypatch.setattr(service, "get_context", _get_context)

    with pytest.raises(HTTPException) as exc_info:
        await service.assert_allowed(tenant, "documents.generate")

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["code"] == "TENANT_SUSPENDED"


@pytest.mark.asyncio
async def test_assert_allowed_enforces_generation_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    service = BillingService(session=None)  # type: ignore[arg-type]
    tenant = Tenant(id="tenant-1", slug="tenant-1", name="Tenant 1", code="tenant-1", schema_name="tenant_1")
    plan = BillingPlan(code="pro", name="Pro", limits={"max_generations_per_month": 2}, features={"edo": True}, price={})
    usage = BillingUsageCounter(tenant_id=tenant.id, period_yyyymm=202603, docs_generated=2)
    context = BillingContext(plan=plan, subscription=None, usage=usage, limits=plan.limits, features=plan.features)

    async def _get_context(_: Tenant) -> BillingContext:
        return context

    monkeypatch.setattr(service, "get_context", _get_context)

    with pytest.raises(HTTPException) as exc_info:
        await service.assert_allowed(tenant, "documents.generate")

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "QUOTA_EXCEEDED"
