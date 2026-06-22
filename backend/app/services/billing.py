from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job_engine import DocumentJob
from app.models.models import (
    AuditLog,
    BillingEvent,
    BillingEventType,
    BillingInvoice,
    BillingPlan,
    BillingSubscription,
    BillingSubscriptionStatus,
    BillingUsageCounter,
    Company,
    Template,
    Tenant,
    TenantLimitOverride,
    User,
)


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
            (
                await self.session.execute(
                    select(BillingSubscription)
                    .where(BillingSubscription.tenant_id == tenant.id)
                    .order_by(BillingSubscription.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        plan = await self.session.get(BillingPlan, subscription.plan_id) if subscription else None
        override = (
            (
                await self.session.execute(
                    select(TenantLimitOverride).where(TenantLimitOverride.tenant_id == tenant.id)
                )
            )
            .scalars()
            .first()
        )
        usage = (
            (
                await self.session.execute(
                    select(BillingUsageCounter).where(
                        BillingUsageCounter.tenant_id == tenant.id,
                        BillingUsageCounter.period_yyyymm == current_period_yyyymm(),
                    )
                )
            )
            .scalars()
            .first()
        )
        limits = dict((plan.limits if plan else {}) or {})
        features = dict((plan.features if plan else {}) or {})
        if override is not None:
            limits.update(override.limits or {})
            features.update(override.features or {})
        return BillingContext(
            plan=plan, subscription=subscription, usage=usage, limits=limits, features=features
        )

    async def ensure_active(self, tenant: Tenant) -> BillingSubscription | None:
        ctx = await self.get_context(tenant)
        sub = ctx.subscription
        if sub is None:
            return None
        now = datetime.now(tz=timezone.utc)
        if sub.status in {BillingSubscriptionStatus.SUSPENDED, BillingSubscriptionStatus.CANCELED}:
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "TENANT_SUSPENDED",
                    "type": "billing",
                    "message": "Tenant subscription is suspended",
                },
            )
        if sub.status == BillingSubscriptionStatus.PAST_DUE:
            if sub.grace_until is None or sub.grace_until < now:
                sub.status = BillingSubscriptionStatus.SUSPENDED
                if self.session is not None:
                    await self.session.flush()
                raise HTTPException(
                    status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "code": "TENANT_SUSPENDED",
                        "type": "billing",
                        "message": "Grace period expired",
                    },
                )
            raise HTTPException(
                status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "TENANT_PAST_DUE",
                    "type": "billing",
                    "message": "Tenant payment past due",
                },
            )
        return sub

    async def ensure_usage_row(
        self, tenant_id: str, period_yyyymm: int | None = None
    ) -> BillingUsageCounter:
        period = period_yyyymm or current_period_yyyymm()
        row = (
            (
                await self.session.execute(
                    select(BillingUsageCounter).where(
                        BillingUsageCounter.tenant_id == tenant_id,
                        BillingUsageCounter.period_yyyymm == period,
                    )
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            row = BillingUsageCounter(tenant_id=tenant_id, period_yyyymm=period)
            self.session.add(row)
            await self.session.flush()
        return row

    async def _count_tenant_entities(self, tenant_id: str, action: str) -> int:
        count_stmt = None
        if action in {"templates.create", "create_template"}:
            count_stmt = select(func.count(Template.id)).where(Template.tenant_id == tenant_id)
        elif action in {"users.create", "create_user"}:
            count_stmt = select(func.count(User.id)).where(
                User.tenant_id == tenant_id, User.deleted_at.is_(None)
            )
        elif action in {"companies.create", "sites.create", "create_company"}:
            count_stmt = select(func.count(Company.id)).where(
                Company.tenant_id == tenant_id, Company.deleted_at.is_(None)
            )
        elif action in {"integrations.enable", "enable_integration"}:
            from app.models.models import TenantIntegrationKey

            count_stmt = select(func.count(TenantIntegrationKey.id)).where(
                TenantIntegrationKey.tenant_id == tenant_id
            )
        if count_stmt is None:
            return 0
        return int((await self.session.execute(count_stmt)).scalar_one() or 0)

    async def check_quota(
        self, tenant: Tenant, action: str, meta: dict[str, Any] | None = None
    ) -> None:
        meta = meta or {}
        ctx = await self.get_context(tenant)
        usage = ctx.usage or await self.ensure_usage_row(tenant.id)
        checks = {
            "templates.create": ("max_templates", None),
            "create_template": ("max_templates", None),
            "start_generation_job": ("max_generations_per_month", "docs_generated"),
            "documents.generate": ("max_generations_per_month", "docs_generated"),
            "create_user": ("max_users", None),
            "edo.send": ("edo_outgoing_per_month", "edo_outgoing"),
            "send_edo": ("edo_outgoing_per_month", "edo_outgoing"),
            "files.upload": ("max_s3_bytes", "s3_bytes_used"),
            "upload_file": ("max_s3_bytes", "s3_bytes_used"),
            "users.create": ("max_users", None),
            "create_company": ("max_companies", None),
            "sites.create": ("max_companies", None),
            "integrations.enable": ("max_integrations", None),
            "enable_integration": ("max_integrations", None),
            "start_generation_job.concurrent": ("max_concurrent_jobs", None),
        }
        limit_key, usage_field = checks.get(action, (None, None))
        if not limit_key:
            return

        if action in {"edo.send", "send_edo"} and not bool(ctx.features.get("edo", True)):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FEATURE_DISABLED",
                    "type": "billing",
                    "message": "Feature unavailable on current plan",
                    "details": {"action": action, "feature": "edo"},
                },
            )

        raw_limit = ctx.limits.get(limit_key)
        if raw_limit in (None, 0):
            if limit_key == "max_templates":
                raw_limit = ctx.limits.get("templates_max")
            elif limit_key == "max_generations_per_month":
                raw_limit = ctx.limits.get("generations_per_month")
        if raw_limit in (None, 0):
            return
        assert raw_limit is not None  # guarded above; satisfies type checker
        limit = int(raw_limit)
        if usage_field == "s3_bytes_used":
            used = int(Decimal(getattr(usage, usage_field) or 0)) + int(
                meta.get("delta_bytes") or 0
            )
        elif usage_field:
            used = int(getattr(usage, usage_field) or 0) + int(meta.get("delta") or 1)
        elif action == "start_generation_job.concurrent":
            used = int(
                (
                    await self.session.execute(
                        select(func.count(DocumentJob.id)).where(
                            DocumentJob.tenant_id == tenant.id,
                            DocumentJob.status.in_(["queued", "running"]),
                        )
                    )
                ).scalar_one()
                or 0
            ) + int(meta.get("delta") or 1)
        else:
            used = await self._count_tenant_entities(tenant.id, action) + int(
                meta.get("delta") or 1
            )

        if used > limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "QUOTA_EXCEEDED",
                    "type": "quota",
                    "message": "Quota exceeded",
                    "details": {"action": action, "limit": limit, "current": used},
                },
            )

    async def assert_allowed(
        self, tenant: Tenant, action: str, meta: dict[str, Any] | None = None
    ) -> None:
        await self.ensure_active(tenant)
        await self.check_quota(tenant, action, meta)

    async def add_billing_event(
        self,
        *,
        tenant_id: str,
        event_type: BillingEventType,
        ref_type: str | None,
        ref_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if ref_id:
            exists = (
                (
                    await self.session.execute(
                        select(BillingEvent).where(
                            BillingEvent.tenant_id == tenant_id,
                            BillingEvent.type == event_type,
                            BillingEvent.ref_type == ref_type,
                            BillingEvent.ref_id == ref_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if exists is not None:
                return False
        self.session.add(
            BillingEvent(
                tenant_id=tenant_id,
                type=event_type,
                ref_type=ref_type,
                ref_id=ref_id,
                payload=payload or {},
            )
        )
        await self.session.flush()
        return True

    async def add_usage(
        self,
        *,
        tenant_id: str,
        docs_generated: int = 0,
        edo_outgoing: int = 0,
        s3_bytes_delta: int = 0,
        period_yyyymm: int | None = None,
        ref_id: str | None = None,
    ) -> BillingUsageCounter:
        usage = await self.ensure_usage_row(tenant_id=tenant_id, period_yyyymm=period_yyyymm)
        if docs_generated:
            recorded = await self.add_billing_event(
                tenant_id=tenant_id,
                event_type=BillingEventType.GENERATION_COMPLETED,
                ref_type="document_job",
                ref_id=ref_id,
                payload={"count": docs_generated},
            )
            if recorded:
                usage.docs_generated = int(usage.docs_generated or 0) + int(docs_generated)
        if edo_outgoing:
            recorded = await self.add_billing_event(
                tenant_id=tenant_id,
                event_type=BillingEventType.EDO_SENT,
                ref_type="edo_message",
                ref_id=ref_id,
                payload={"count": edo_outgoing},
            )
            if recorded:
                usage.edo_outgoing = int(usage.edo_outgoing or 0) + int(edo_outgoing)
        updated_bytes = int(usage.s3_bytes_used or 0) + int(s3_bytes_delta)
        usage.s3_bytes_used = max(updated_bytes, 0)
        await self.session.flush()
        return usage

    async def switch_plan(
        self, tenant: Tenant, plan_code: str, *, actor_user_id: str | None, correlation_id: str
    ) -> BillingSubscription:
        plan = (
            (await self.session.execute(select(BillingPlan).where(BillingPlan.code == plan_code)))
            .scalars()
            .first()
        )
        if plan is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "PLAN_NOT_FOUND", "message": "Plan not found"},
            )
        sub = (
            (
                await self.session.execute(
                    select(BillingSubscription)
                    .where(BillingSubscription.tenant_id == tenant.id)
                    .order_by(BillingSubscription.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        now = datetime.now(tz=timezone.utc)
        if sub is None:
            sub = BillingSubscription(
                tenant_id=tenant.id,
                plan_id=plan.id,
                status=BillingSubscriptionStatus.ACTIVE,
                period_start=now,
                period_end=now + timedelta(days=30),
                auto_renew=True,
            )
            self.session.add(sub)
        else:
            sub.plan_id = plan.id
            sub.updated_at = now
        await self.add_billing_event(
            tenant_id=tenant.id,
            event_type=BillingEventType.PLAN_CHANGED,
            ref_type="subscription",
            ref_id=sub.id,
            payload={"plan_code": plan_code},
        )
        self.session.add(
            AuditLog(
                tenant_id=tenant.id,
                action="billing.plan_changed",
                object_type="subscription",
                object_id=sub.id,
                user_id=actor_user_id,
                ip="api",
                correlation_id=correlation_id,
                details={"plan_code": plan_code},
                resource_attrs={},
                changed_fields={"plan_code": plan_code},
                actor_role_codes=[],
                hash="",
            )
        )
        await self.session.flush()
        return sub

    @staticmethod
    def compute_remaining(
        limits: dict[str, Any], usage: BillingUsageCounter | None
    ) -> dict[str, int | None]:
        usage = usage or BillingUsageCounter(tenant_id="", period_yyyymm=current_period_yyyymm())
        generation_limit = limits.get(
            "max_generations_per_month", limits.get("generations_per_month")
        )
        fields = {
            "max_generations_per_month": int(usage.docs_generated or 0),
            "edo_outgoing_per_month": int(usage.edo_outgoing or 0),
            "max_s3_bytes": int(usage.s3_bytes_used or 0),
        }
        out: dict[str, int | None] = {}
        for key, used in fields.items():
            limit = limits.get(key)
            if key == "max_generations_per_month":
                limit = generation_limit
            if limit is None:
                out[key] = None
            else:
                out[key] = max(int(limit) - used, 0)
        if generation_limit is not None:
            out["generations_per_month"] = out["max_generations_per_month"]
        return out

    async def list_events(
        self, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[BillingEvent]:
        stmt = (
            select(BillingEvent)
            .where(BillingEvent.tenant_id == tenant_id)
            .order_by(BillingEvent.created_at.desc())
            .offset(max(offset, 0))
            .limit(max(1, min(limit, 200)))
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_invoices(
        self, tenant_id: str, period_yyyymm: int | None = None
    ) -> list[BillingInvoice]:
        stmt = (
            select(BillingInvoice)
            .where(BillingInvoice.tenant_id == tenant_id)
            .order_by(BillingInvoice.period_yyyymm.desc())
        )
        if period_yyyymm is not None:
            stmt = stmt.where(BillingInvoice.period_yyyymm == period_yyyymm)
        return list((await self.session.execute(stmt)).scalars().all())
