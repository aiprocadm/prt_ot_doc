from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.models.models import BillingSubscription, BillingSubscriptionStatus, Tenant
from app.schemas.billing import (
    BillingChangePlanRequest,
    BillingEventRead,
    BillingInvoiceRead,
    BillingPlanRead,
    BillingStatusMutationRequest,
    BillingSummaryRead,
)
from app.services.billing import BillingService, current_period_yyyymm

router = APIRouter(prefix="/billing", tags=["billing"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _billing_bad_request(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": message},
    )


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


OwnerAdminAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")),
]


@router.get("/plan", response_model=BillingSummaryRead)
async def billing_plan(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> BillingSummaryRead:
    _ = access
    service = BillingService(session)
    ctx = await service.get_context(tenant)
    remaining = BillingService.compute_remaining(ctx.limits, ctx.usage)
    return BillingSummaryRead(
        plan={"code": ctx.plan.code, "name": ctx.plan.name} if ctx.plan else {"code": "free", "name": "Free"},
        subscription={
            "status": ctx.subscription.status.value,
            "period_start": ctx.subscription.period_start,
            "period_end": ctx.subscription.period_end,
            "grace_until": ctx.subscription.grace_until,
            "auto_renew": ctx.subscription.auto_renew,
        }
        if ctx.subscription
        else {"status": "trial", "period_start": None, "period_end": None, "grace_until": None, "auto_renew": False},
        limits=ctx.limits,
        features=ctx.features,
        usage={
            "period_yyyymm": ctx.usage.period_yyyymm if ctx.usage else current_period_yyyymm(),
            "docs_generated": int(ctx.usage.docs_generated) if ctx.usage else 0,
            "edo_outgoing": int(ctx.usage.edo_outgoing) if ctx.usage else 0,
            "s3_bytes_used": int(ctx.usage.s3_bytes_used) if ctx.usage else 0,
            "active_workers": int(ctx.usage.active_workers) if ctx.usage else 0,
        },
        remaining=remaining,
    )


@router.get("/usage")
async def billing_usage(
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
    period: int | None = None,
) -> dict[str, Any]:
    _ = access
    service = BillingService(session)
    ctx = await service.get_context(tenant)
    selected_period = period or current_period_yyyymm()
    if ctx.usage is None or ctx.usage.period_yyyymm != selected_period:
        usage = await service.ensure_usage_row(tenant.id, selected_period)
    else:
        usage = ctx.usage
    usage_payload = {
        "generations_count": int(usage.docs_generated or 0),
        "edo_outgoing_count": int(usage.edo_outgoing or 0),
        "active_workers_count": int(usage.active_workers or 0),
        "s3_bytes_used": int(usage.s3_bytes_used or 0),
    }
    percentages: dict[str, float | None] = {}
    for usage_key, limit_key in {
        "generations_count": "max_generations_per_month",
        "edo_outgoing_count": "edo_outgoing_per_month",
        "active_workers_count": "max_users",
        "s3_bytes_used": "max_s3_bytes",
    }.items():
        raw_limit = ctx.limits.get(limit_key)
        if raw_limit in (None, 0):
            percentages[usage_key] = None
            continue
        percentages[usage_key] = round((float(usage_payload[usage_key]) / float(raw_limit)) * 100, 2)

    return {
        "period": selected_period,
        "usage": usage_payload,
        "limits": ctx.limits,
        "percentages": percentages,
    }


@router.get("/events", response_model=list[BillingEventRead])
async def billing_events(
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
    limit: int = 50,
    offset: int = 0,
) -> list[BillingEventRead]:
    _ = access
    items = await BillingService(session).list_events(tenant.id, limit=limit, offset=offset)
    return [
        BillingEventRead(
            id=item.id,
            event_type=item.type.value if hasattr(item.type, "value") else str(item.type),
            payload=item.payload or {},
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/limits")
async def billing_limits(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> dict[str, Any]:
    _ = access
    ctx = await BillingService(session).get_context(tenant)
    return {"plan": ctx.plan.code if ctx.plan else "free", "limits": ctx.limits, "features": ctx.features}


@router.get("/plans", response_model=list[BillingPlanRead])
async def billing_plans(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> list[BillingPlanRead]:
    _ = (tenant, access)
    from app.models.models import BillingPlan

    plans = list((await session.execute(select(BillingPlan).order_by(BillingPlan.name.asc()))).scalars().all())
    return [BillingPlanRead(code=item.code, name=item.name, limits=item.limits or {}, features=item.features or {}) for item in plans]


@router.post("/plan/change")
@audit_operation("change_plan", "billing_subscription")
async def change_plan(
    payload: BillingChangePlanRequest,
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not idempotency_key:
        raise _billing_bad_request("IDEMPOTENCY_REQUIRED", "Idempotency-Key required")
    sub = await BillingService(session).switch_plan(
        tenant,
        payload.plan_code,
        actor_user_id=getattr(access.user, "id", None) if access else None,
        correlation_id=idempotency_key,
    )
    await session.commit()
    return {"status": "ok", "subscription_id": sub.id, "plan_code": payload.plan_code}


@router.post("/subscription/mark_past_due")
@audit_operation("mark_past_due", "billing_subscription")
async def mark_past_due(
    payload: BillingStatusMutationRequest,
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
) -> dict[str, str]:
    _ = access
    sub = (await session.execute(select(BillingSubscription).where(BillingSubscription.tenant_id == tenant.id).order_by(BillingSubscription.created_at.desc()))).scalars().first()
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"})
    sub.status = BillingSubscriptionStatus.PAST_DUE
    sub.grace_until = datetime.now(tz=timezone.utc) + timedelta(days=payload.grace_days)
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/mark_paid")
@audit_operation("mark_paid", "billing_subscription")
async def mark_paid(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> dict[str, str]:
    _ = access
    sub = (await session.execute(select(BillingSubscription).where(BillingSubscription.tenant_id == tenant.id).order_by(BillingSubscription.created_at.desc()))).scalars().first()
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"})
    sub.status = BillingSubscriptionStatus.ACTIVE
    sub.grace_until = None
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/suspend")
@audit_operation("suspend", "billing_subscription")
async def suspend(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> dict[str, str]:
    _ = access
    sub = (await session.execute(select(BillingSubscription).where(BillingSubscription.tenant_id == tenant.id).order_by(BillingSubscription.created_at.desc()))).scalars().first()
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"})
    sub.status = BillingSubscriptionStatus.SUSPENDED
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/activate")
@audit_operation("activate", "billing_subscription")
async def activate(session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)) -> dict[str, str]:
    _ = access
    sub = (await session.execute(select(BillingSubscription).where(BillingSubscription.tenant_id == tenant.id).order_by(BillingSubscription.created_at.desc()))).scalars().first()
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"})
    sub.status = BillingSubscriptionStatus.ACTIVE
    await session.commit()
    return {"status": "ok"}


@router.get("/invoices", response_model=list[BillingInvoiceRead])
async def billing_invoices(
    session: SessionDep,
    access: OwnerAdminAccess,
    tenant: Tenant = Depends(get_tenant_record),
    period: int | None = None,
) -> list[BillingInvoiceRead]:
    _ = access
    items = await BillingService(session).list_invoices(tenant.id, period)
    return [BillingInvoiceRead.model_validate(item) for item in items]
