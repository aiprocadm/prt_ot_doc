from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import (
    AuditLog,
    BillingPlan,
    BillingSubscription,
    Tenant,
    TenantLimitOverride,
)
from app.schemas.billing import (
    BillingChangePlanRequest,
    BillingInvoiceRead,
    BillingOverrideRequest,
    BillingSummaryRead,
)
from app.services.billing import BillingService
from app.services.outbox import OutboxService
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/billing", tags=["billing"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


OwnerAdminAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")),
]


@router.get("/summary", response_model=BillingSummaryRead)
async def billing_summary(session: SessionDep, tenant: Tenant = Depends(get_tenant_record), access: OwnerAdminAccess = None) -> BillingSummaryRead:
    _ = access
    service = BillingService(session)
    ctx = await service.get_context(tenant)
    remaining = BillingService.compute_remaining(ctx.limits, ctx.usage)
    return BillingSummaryRead(
        plan={"code": ctx.plan.code, "name": ctx.plan.name} if ctx.plan else {"code": "free", "name": "Free"},
        subscription={
            "status": ctx.subscription.status.value,
            "period_end": ctx.subscription.period_end,
            "grace_until": ctx.subscription.grace_until,
            "auto_renew": ctx.subscription.auto_renew,
        }
        if ctx.subscription
        else {"status": "trial", "period_end": None, "grace_until": None, "auto_renew": False},
        limits=ctx.limits,
        features=ctx.features,
        usage={
            "period_yyyymm": ctx.usage.period_yyyymm if ctx.usage else None,
            "docs_generated": int(ctx.usage.docs_generated) if ctx.usage else 0,
            "edo_outgoing": int(ctx.usage.edo_outgoing) if ctx.usage else 0,
            "s3_bytes_used": int(ctx.usage.s3_bytes_used) if ctx.usage else 0,
            "active_workers": int(ctx.usage.active_workers) if ctx.usage else 0,
        },
        remaining=remaining,
    )


@router.post("/change-plan")
async def change_plan(
    payload: BillingChangePlanRequest,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: OwnerAdminAccess = None,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    _ = access
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail={"code": "IDEMPOTENCY_REQUIRED", "message": "Idempotency-Key required"})
    plan = (await session.execute(select(BillingPlan).where(BillingPlan.code == payload.plan_code))).scalars().first()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Plan not found")
    sub = (
        await session.execute(select(BillingSubscription).where(BillingSubscription.tenant_id == tenant.id).order_by(BillingSubscription.created_at.desc()))
    ).scalars().first()
    now = datetime.now(tz=timezone.utc)
    if sub is None:
        sub = BillingSubscription(
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="active",
            period_start=now,
            period_end=now,
            auto_renew=True,
        )
        session.add(sub)
    else:
        if sub.plan_id == plan.id:
            return {"status": "ok", "idempotent": True}
        sub.plan_id = plan.id
        sub.updated_at = now

    session.add(
        AuditLog(
            tenant_id=tenant.id,
            action="billing.plan_changed",
            object_type="subscription",
            object_id=sub.id,
            user_id=getattr(access.user, "id", None) if access else None,
            ip="api",
            correlation_id=idempotency_key,
            details={"plan_code": payload.plan_code},
            resource_attrs={},
            changed_fields={"plan_code": payload.plan_code},
            actor_role_codes=[],
            hash="",
        )
    )
    await OutboxService(session).enqueue(
        tenant_id=tenant.id,
        event_type="PlanChanged",
        payload={"tenant_id": tenant.id, "plan_code": payload.plan_code, "event_id": idempotency_key},
        idempotency_key=f"plan-change:{tenant.id}:{idempotency_key}",
    )
    await session.commit()
    return {"status": "ok", "plan_code": payload.plan_code}


@router.get("/invoices", response_model=list[BillingInvoiceRead])
async def billing_invoices(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: OwnerAdminAccess = None,
    period: int | None = None,
) -> list[BillingInvoiceRead]:
    _ = access
    items = await BillingService(session).list_invoices(tenant.id, period)
    return [BillingInvoiceRead.model_validate(item) for item in items]


@router.post("/override")
async def billing_override(
    payload: BillingOverrideRequest,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: OwnerAdminAccess = None,
    x_platform_admin: str | None = Header(default=None, alias="X-Platform-Admin"),
) -> dict[str, str]:
    _ = access
    if x_platform_admin != "true":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "FORBIDDEN", "message": "platform admin required"})
    override = (await session.execute(select(TenantLimitOverride).where(TenantLimitOverride.tenant_id == tenant.id))).scalars().first()
    now = datetime.now(tz=timezone.utc)
    if override is None:
        override = TenantLimitOverride(
            tenant_id=tenant.id,
            limits=payload.limits,
            features=payload.features,
            effective_from=now,
        )
        session.add(override)
    else:
        override.limits = payload.limits
        override.features = payload.features
        override.effective_from = now
    await session.commit()
    return {"status": "ok"}
