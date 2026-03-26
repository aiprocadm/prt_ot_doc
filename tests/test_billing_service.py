from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.models import (
    BillingPlan,
    BillingSubscription,
    BillingSubscriptionStatus,
    BillingUsageCounter,
    Tenant,
)
from app.services.billing import BillingService


class _StubSession:
    def __init__(self, *, tenant: Tenant, plan: BillingPlan, sub: BillingSubscription, usage: BillingUsageCounter):
        self._tenant = tenant
        self._plan = plan
        self._sub = sub
        self._usage = usage

    async def execute(self, stmt):  # noqa: ANN001
        class _Res:
            def __init__(self, value):
                self._value = value

            def scalars(self):
                return self

            def first(self):
                return self._value

            def all(self):
                return [self._value] if self._value is not None else []

            def scalar_one(self):
                return self._value

        text = str(stmt)
        if "FROM subscriptions" in text:
            return _Res(self._sub)
        if "FROM tenant_limits_override" in text:
            return _Res(None)
        if "FROM usage_counters" in text:
            return _Res(self._usage)
        if "count(template.id)" in text:
            return _Res(10)
        return _Res(None)

    async def get(self, model, _id):  # noqa: ANN001
        if model.__name__ == "BillingPlan":
            return self._plan
        return None

    def add(self, _obj):  # noqa: ANN001
        return None

    async def flush(self):
        return None


def _prepare(status: BillingSubscriptionStatus, grace_delta_days: int = -1):
    tenant = Tenant(id="t1", slug="t", name="T", contact_email="a@b.c", kind="customer", is_active=True, settings={})
    plan = BillingPlan(code="pro", name="Pro", limits={"generations_per_month": 10}, features={"edo": True}, price={})
    sub = BillingSubscription(
        tenant_id="t1",
        plan_id="p1",
        status=status,
        period_start=datetime.now(tz=timezone.utc),
        period_end=datetime.now(tz=timezone.utc),
        auto_renew=True,
        grace_until=datetime.now(tz=timezone.utc) + timedelta(days=grace_delta_days),
    )
    usage = BillingUsageCounter(tenant_id="t1", period_yyyymm=202603, docs_generated=9)
    return tenant, plan, sub, usage


@pytest.mark.asyncio
async def test_assert_allowed_blocks_past_due_after_grace() -> None:
    tenant, plan, sub, usage = _prepare(BillingSubscriptionStatus.PAST_DUE, grace_delta_days=-1)
    service = BillingService(_StubSession(tenant=tenant, plan=plan, sub=sub, usage=usage))
    with pytest.raises(HTTPException) as exc:
        await service.assert_allowed(tenant, "documents.generate")
    assert exc.value.detail["code"] == "TENANT_SUSPENDED"


def test_compute_remaining() -> None:
    usage = BillingUsageCounter(tenant_id="t1", period_yyyymm=202603, docs_generated=5, edo_outgoing=3)
    remaining = BillingService.compute_remaining({"generations_per_month": 10, "edo_outgoing_per_month": 5}, usage)
    assert remaining["generations_per_month"] == 5
    assert remaining["edo_outgoing_per_month"] == 2


@pytest.mark.asyncio
async def test_assert_allowed_blocks_disabled_feature() -> None:
    tenant, plan, sub, usage = _prepare(BillingSubscriptionStatus.ACTIVE, grace_delta_days=5)
    plan.features = {"edo": False}
    service = BillingService(_StubSession(tenant=tenant, plan=plan, sub=sub, usage=usage))
    with pytest.raises(HTTPException) as exc:
        await service.assert_allowed(tenant, "edo.send")
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "FEATURE_DISABLED"


@pytest.mark.asyncio
async def test_assert_allowed_blocks_template_limit() -> None:
    tenant, plan, sub, usage = _prepare(BillingSubscriptionStatus.ACTIVE, grace_delta_days=5)
    plan.limits = {"templates_max": 10}
    service = BillingService(_StubSession(tenant=tenant, plan=plan, sub=sub, usage=usage))
    with pytest.raises(HTTPException) as exc:
        await service.assert_allowed(tenant, "templates.create")
    assert exc.value.status_code == 429
    assert exc.value.detail["code"] == "QUOTA_EXCEEDED"
