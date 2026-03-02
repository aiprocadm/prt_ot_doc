from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.models.models import BillingEventType, BillingSubscriptionStatus, Tenant
from app.services.billing import BillingService, current_period_yyyymm
from fastapi import HTTPException


@dataclass(slots=True)
class QuotaExceeded(Exception):
    code: str
    details: dict[str, Any]


class QuotasService:
    def __init__(self, billing_service: BillingService) -> None:
        self.billing_service = billing_service

    async def get_limits(self, tenant_id: str) -> dict[str, Any]:
        tenant = await self.billing_service.session.get(Tenant, tenant_id)
        if tenant is None:
            return {}
        return (await self.billing_service.get_context(tenant)).limits

    async def check_quota(self, tenant: Tenant, action: str, delta: int = 1, context: dict[str, Any] | None = None) -> None:
        meta = dict(context or {})
        meta.setdefault("delta", delta)
        try:
            await self.billing_service.check_quota(tenant, action, meta)
        except HTTPException as exc:
            if isinstance(exc.detail, dict) and exc.detail.get("code") == "QUOTA_EXCEEDED":
                raise QuotaExceeded(code="QUOTA_EXCEEDED", details=exc.detail.get("details", {})) from exc
            raise


class SubscriptionService:
    def __init__(self, billing_service: BillingService) -> None:
        self.billing_service = billing_service

    async def ensure_active(self, tenant: Tenant) -> None:
        await self.billing_service.ensure_active(tenant)

    async def normalize_past_due(self, tenant: Tenant) -> BillingSubscriptionStatus | None:
        ctx = await self.billing_service.get_context(tenant)
        if ctx.subscription is None:
            return None
        if ctx.subscription.status is BillingSubscriptionStatus.PAST_DUE:
            grace_until = ctx.subscription.grace_until
            now = datetime.now(tz=timezone.utc)
            if grace_until is None or now > grace_until:
                ctx.subscription.status = BillingSubscriptionStatus.SUSPENDED
                await self.billing_service.session.flush()
        return ctx.subscription.status


class UsageCountersService:
    def __init__(self, billing_service: BillingService) -> None:
        self.billing_service = billing_service

    async def inc_generation(self, tenant_id: str, count: int = 1, period: int | None = None, ref_id: str | None = None) -> None:
        await self.billing_service.add_usage(tenant_id=tenant_id, docs_generated=count, period_yyyymm=period or current_period_yyyymm(), ref_id=ref_id)

    async def inc_edo_outgoing(self, tenant_id: str, count: int = 1, period: int | None = None, ref_id: str | None = None) -> None:
        await self.billing_service.add_usage(tenant_id=tenant_id, edo_outgoing=count, period_yyyymm=period or current_period_yyyymm(), ref_id=ref_id)

    async def set_snapshot_active_workers(self, tenant_id: str, value: int, period: int | None = None) -> None:
        usage = await self.billing_service.ensure_usage_row(tenant_id=tenant_id, period_yyyymm=period or current_period_yyyymm())
        usage.active_workers = value
        await self.billing_service.session.flush()

    async def update_s3_bytes_used(self, tenant_id: str, bytes_used: int, period: int | None = None) -> None:
        usage = await self.billing_service.ensure_usage_row(tenant_id=tenant_id, period_yyyymm=period or current_period_yyyymm())
        usage.s3_bytes_used = max(int(bytes_used), 0)
        await self.billing_service.add_billing_event(
            tenant_id=tenant_id,
            event_type=BillingEventType.FILE_UPLOADED,
            ref_type="s3_snapshot",
            ref_id=f"{tenant_id}:{usage.period_yyyymm}",
            payload={"bytes_used": usage.s3_bytes_used},
        )
        await self.billing_service.session.flush()
