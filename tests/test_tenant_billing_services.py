from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app.models.models import BillingPlan, BillingSubscription, BillingSubscriptionStatus, BillingUsageCounter, Tenant
from app.services.billing import BillingService
from app.services.tenant_billing import QuotaExceeded, QuotasService, SubscriptionService, UsageCountersService
from fastapi import HTTPException


class _Session:
    def __init__(self, tenant: Tenant, plan: BillingPlan, sub: BillingSubscription, usage: BillingUsageCounter):
        self.tenant = tenant
        self.plan = plan
        self.sub = sub
        self.usage = usage
        self._events: set[tuple[str, str, str, str]] = set()

    async def execute(self, stmt):  # noqa: ANN001
        class _Res:
            def __init__(self, value):
                self.value = value

            def scalars(self):
                return self

            def first(self):
                return self.value

            def scalar_one(self):
                return self.value

        text = str(stmt)
        if "FROM subscriptions" in text:
            return _Res(self.sub)
        if "FROM tenant_limits_override" in text:
            return _Res(None)
        if "FROM usage_counters" in text:
            return _Res(self.usage)
        if "count(template.id)" in text:
            return _Res(0)
        if "FROM billing_events" in text:
            params = stmt.compile().params
            tenant_id = str(params.get("tenant_id_1", ""))
            ref_id = str(params.get("ref_id_1", ""))
            type_ = str(params.get("type_1", ""))
            ref_type = str(params.get("ref_type_1", ""))
            if (tenant_id, type_, ref_type, ref_id) in self._events:
                return _Res(object())
            return _Res(None)
        return _Res(None)

    async def get(self, model, _id):  # noqa: ANN001
        if model.__name__ == "BillingPlan":
            return self.plan
        if model.__name__ == "Tenant":
            return self.tenant
        return None

    def add(self, obj):  # noqa: ANN001
        if obj.__class__.__name__ == "BillingEvent":
            self._events.add((obj.tenant_id, str(obj.type), str(obj.ref_type or ""), str(obj.ref_id or "")))
        elif obj.__class__.__name__ == "BillingUsageCounter":
            self.usage = obj
        return None

    async def flush(self):
        return None


@pytest.fixture
def fixture() -> tuple[BillingService, Tenant]:
    tenant = Tenant(id="tenant-1", slug="t1", name="Tenant", contact_email="t@a.b", kind="customer", is_active=True, settings={})
    plan = BillingPlan(code="free", name="Free", limits={"max_templates": 1}, features={}, price={})
    sub = BillingSubscription(
        tenant_id=tenant.id,
        plan_id="plan-1",
        status=BillingSubscriptionStatus.PAST_DUE,
        period_start=datetime.now(tz=timezone.utc),
        period_end=datetime.now(tz=timezone.utc) + timedelta(days=30),
        grace_until=datetime.now(tz=timezone.utc) - timedelta(days=1),
        auto_renew=True,
    )
    usage = BillingUsageCounter(tenant_id=tenant.id, period_yyyymm=202603, docs_generated=0, edo_outgoing=0)
    return BillingService(_Session(tenant, plan, sub, usage)), tenant


@pytest.mark.asyncio
async def test_subscription_service_rolls_past_due_into_suspended(fixture) -> None:
    billing, tenant = fixture
    service = SubscriptionService(billing)
    status = await service.normalize_past_due(tenant)
    assert status == BillingSubscriptionStatus.SUSPENDED


@pytest.mark.asyncio
async def test_quotas_service_raises_quota_exceeded(fixture) -> None:
    billing, tenant = fixture
    tenant_sub = billing.session.sub
    tenant_sub.status = BillingSubscriptionStatus.ACTIVE
    quotas = QuotasService(billing)
    with pytest.raises(QuotaExceeded):
        await quotas.check_quota(tenant, "create_template", delta=2)


@pytest.mark.asyncio
async def test_usage_counter_idempotent_ref_id(fixture) -> None:
    billing, tenant = fixture
    billing.session.sub.status = BillingSubscriptionStatus.ACTIVE
    counters = UsageCountersService(billing)
    await counters.inc_generation(tenant.id, count=1, ref_id="job-1")
    first = int(billing.session.usage.docs_generated)
    await counters.inc_generation(tenant.id, count=1, ref_id="job-1")
    second = int(billing.session.usage.docs_generated)
    assert first == second
