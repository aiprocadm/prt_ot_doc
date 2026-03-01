from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.models.models import (
    Company,
    BillingInvoice,
    BillingPlan,
    BillingSubscription,
    BillingSubscriptionStatus,
    BillingUsageCounter,
    Template,
    Tenant,
    TenantLimitOverride,
    User,
)
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BillingContext:
    plan: BillingPlan | None
    subscription: BillingSubscription | None
    usage: BillingUsageCounter | None
    limits: dict[str, Any]
    features: dict[str, Any]


def current_period_yyyymm(now: datetime | None = None) -> int:
    value = now or datetime.now(tz=timezone.utc)
    return int(value.strftime("%Y%m"))


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_context(self, tenant: Tenant) -> BillingContext:
        subscription = (
            await self.session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.tenant_id == tenant.id)
                .order_by(BillingSubscription.created_at.desc())
            )
        ).scalars().first()
        plan = await self.session.get(BillingPlan, subscription.plan_id) if subscription else None
        override = (
            await self.session.execute(
                select(TenantLimitOverride).where(TenantLimitOverride.tenant_id == tenant.id)
            )
        ).scalars().first()
        usage = (
            await self.session.execute(
                select(BillingUsageCounter).where(
                    BillingUsageCounter.tenant_id == tenant.id,
                    BillingUsageCounter.period_yyyymm == current_period_yyyymm(),
                )
            )
        ).scalars().first()
        limits = dict((plan.limits if plan else {}) or {})
        features = dict((plan.features if plan else {}) or {})
        if override is not None:
            limits.update(override.limits or {})
            features.update(override.features or {})
        return BillingContext(plan=plan, subscription=subscription, usage=usage, limits=limits, features=features)

    async def ensure_usage_row(self, tenant_id: str, period_yyyymm: int | None = None) -> BillingUsageCounter:
        period = period_yyyymm or current_period_yyyymm()
        row = (
            await self.session.execute(
                select(BillingUsageCounter).where(
                    BillingUsageCounter.tenant_id == tenant_id,
                    BillingUsageCounter.period_yyyymm == period,
                )
            )
        ).scalars().first()
        if row is None:
            row = BillingUsageCounter(tenant_id=tenant_id, period_yyyymm=period)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _count_tenant_entities(self, tenant_id: str, action: str) -> int:
        count_stmt = None
        if action == "templates.create":
            count_stmt = select(func.count(Template.id)).where(Template.tenant_id == tenant_id)
        elif action == "users.create":
            count_stmt = select(func.count(User.id)).where(User.tenant_id == tenant_id, User.deleted_at.is_(None))
        elif action == "contractors.create":
            count_stmt = select(func.count(Company.id)).where(Company.tenant_id == tenant_id, Company.deleted_at.is_(None))
        if count_stmt is None:
            return 0
        return int((await self.session.execute(count_stmt)).scalar_one() or 0)

    async def assert_allowed(self, tenant: Tenant, action: str, meta: dict[str, Any] | None = None) -> None:
        meta = meta or {}
        ctx = await self.get_context(tenant)
        now = datetime.now(tz=timezone.utc)
        sub = ctx.subscription
        if sub is not None:
            blocked = sub.status in {BillingSubscriptionStatus.SUSPENDED, BillingSubscriptionStatus.CANCELED}
            overdue = sub.status is BillingSubscriptionStatus.PAST_DUE and (sub.grace_until is None or sub.grace_until < now)
            if blocked or overdue:
                raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, detail={"code": "BILLING_BLOCKED", "message": "Tenant billing is blocked"})

        feature_map = {
            "edo.send": "edo",
            "integrations.use": "integrations_1c",
        }
        feature_key = feature_map.get(action)
        if feature_key is not None and ctx.features.get(feature_key) is False:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "FEATURE_DISABLED", "message": "Feature is disabled", "meta": {"feature": feature_key}})

        usage = ctx.usage or await self.ensure_usage_row(tenant.id)
        checks = {
            "templates.create": ("templates_max", None),
            "documents.generate": ("generations_per_month", "docs_generated"),
            "edo.send": ("edo_outgoing_per_month", "edo_outgoing"),
            "files.upload": ("s3_gb_max", "s3_bytes_used"),
            "users.create": ("users_max", None),
            "contractors.create": ("contractors_max", None),
        }
        limit_key, usage_field = checks.get(action, (None, None))
        if not limit_key:
            return
        raw_limit = ctx.limits.get(limit_key)
        if raw_limit in (None, 0):
            return
        limit = int(raw_limit)
        if usage_field == "s3_bytes_used":
            limit = limit * 1024 * 1024 * 1024
            used = int(Decimal(getattr(usage, usage_field) or 0)) + int(meta.get("delta_bytes") or 0)
        elif usage_field:
            used = int(getattr(usage, usage_field) or 0) + int(meta.get("delta") or 1)
        else:
            used = await self._count_tenant_entities(tenant.id, action) + int(meta.get("delta") or 1)
        if used > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "QUOTA_EXCEEDED", "message": "Quota exceeded", "meta": {"action": action, "limit": limit, "used": used}})

    async def add_usage(
        self,
        *,
        tenant_id: str,
        docs_generated: int = 0,
        edo_outgoing: int = 0,
        s3_bytes_delta: int = 0,
        period_yyyymm: int | None = None,
    ) -> BillingUsageCounter:
        usage = await self.ensure_usage_row(tenant_id=tenant_id, period_yyyymm=period_yyyymm)
        usage.docs_generated = int(usage.docs_generated or 0) + int(docs_generated)
        usage.edo_outgoing = int(usage.edo_outgoing or 0) + int(edo_outgoing)
        updated_bytes = int(usage.s3_bytes_used or 0) + int(s3_bytes_delta)
        usage.s3_bytes_used = max(updated_bytes, 0)
        await self.session.flush()
        return usage

    @staticmethod
    def compute_remaining(limits: dict[str, Any], usage: BillingUsageCounter | None) -> dict[str, int | None]:
        usage = usage or BillingUsageCounter(tenant_id="", period_yyyymm=current_period_yyyymm())
        fields = {
            "generations_per_month": int(usage.docs_generated or 0),
            "edo_outgoing_per_month": int(usage.edo_outgoing or 0),
            "s3_gb_max": int((Decimal(usage.s3_bytes_used or 0) / Decimal(1024 ** 3)).quantize(Decimal("1"))),
        }
        out: dict[str, int | None] = {}
        for key, used in fields.items():
            if limits.get(key) is None:
                out[key] = None
            else:
                out[key] = max(int(limits[key]) - used, 0)
        return out

    async def list_invoices(self, tenant_id: str, period_yyyymm: int | None = None) -> list[BillingInvoice]:
        stmt = select(BillingInvoice).where(BillingInvoice.tenant_id == tenant_id).order_by(BillingInvoice.period_yyyymm.desc())
        if period_yyyymm is not None:
            stmt = stmt.where(BillingInvoice.period_yyyymm == period_yyyymm)
        return list((await self.session.execute(stmt)).scalars().all())
