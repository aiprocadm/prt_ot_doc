from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.domains.reseller import revenue
from app.models.models import BillingSubscription, BillingSubscriptionStatus, Tenant
from app.models.tenant_billing import ResellerPrice
from app.modules.subscription.editions import EDITIONS
from app.schemas.billing import (
    BillingChangePlanRequest,
    BillingEditionRead,
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
        detail=api_problem_detail(code=code, message=message, error_type="billing"),
    )


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


OwnerAdminAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")),
]


@router.get("/plan", response_model=BillingSummaryRead)
async def billing_plan(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> BillingSummaryRead:
    _ = access
    service = BillingService(session)
    ctx = await service.get_context(tenant)
    remaining = BillingService.compute_remaining(ctx.limits, ctx.usage)
    return BillingSummaryRead(
        plan=(
            {"code": ctx.plan.code, "name": ctx.plan.name}
            if ctx.plan
            else {"code": "free", "name": "Free"}
        ),
        subscription=(
            {
                "status": ctx.subscription.status.value,
                "period_start": ctx.subscription.period_start,
                "period_end": ctx.subscription.period_end,
                "grace_until": ctx.subscription.grace_until,
                "auto_renew": ctx.subscription.auto_renew,
            }
            if ctx.subscription
            else {
                "status": "trial",
                "period_start": None,
                "period_end": None,
                "grace_until": None,
                "auto_renew": False,
            }
        ),
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
    # Срез-121: у работников лимита НЕТ. `max_users` ограничивает учётные
    # записи (квота считает строки `User`, см. billing._count_tenant_entities),
    # а здесь считаются сотрудники — делить одно на другое значит показывать
    # выдуманный процент: у арендатора со 100 сотрудниками и лимитом в 20
    # входов на экране горело «500%». Нет лимита — нет процента.
    percentages["active_workers_count"] = None
    for usage_key, limit_key in {
        "generations_count": "max_generations_per_month",
        "edo_outgoing_count": "edo_outgoing_per_month",
        "s3_bytes_used": "max_s3_bytes",
    }.items():
        raw_limit = ctx.limits.get(limit_key)
        if raw_limit in (None, 0):
            percentages[usage_key] = None
            continue
        percentages[usage_key] = round(
            (float(usage_payload[usage_key]) / float(raw_limit)) * 100, 2
        )

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
async def billing_limits(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> dict[str, Any]:
    _ = access
    ctx = await BillingService(session).get_context(tenant)
    return {
        "plan": ctx.plan.code if ctx.plan else "free",
        "limits": ctx.limits,
        "features": ctx.features,
    }


@router.get("/plans", response_model=list[BillingPlanRead])
async def billing_plans(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> list[BillingPlanRead]:
    _ = (tenant, access)
    from app.models.models import BillingPlan

    plans = list(
        (await session.execute(select(BillingPlan).order_by(BillingPlan.name.asc())))
        .scalars()
        .all()
    )
    return [
        BillingPlanRead(
            code=item.code, name=item.name, limits=item.limits or {}, features=item.features or {}
        )
        for item in plans
    ]


@router.get("/editions", response_model=list[BillingEditionRead])
async def billing_editions(
    access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> list[BillingEditionRead]:
    """Редакции под размер заказчика (разд. 53.1).

    Список статический: это продуктовая упаковка тарифов, а не данные
    арендатора. Две редакции могут ссылаться на ОДИН тариф — тогда та, что
    делит его с другой, объясняет отличие словами (SSO, on-prem, SLA), потому
    что модулями они не различаются.
    """

    _ = (tenant, access)
    return [
        BillingEditionRead(
            code=item.code,
            title=item.title,
            audience=item.audience,
            plan_code=item.plan_code,
            includes=item.includes,
            beyond_modules=item.beyond_modules,
        )
        for item in EDITIONS
    ]


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
    sub = (
        (
            await session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.tenant_id == tenant.id)
                .order_by(BillingSubscription.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if sub is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"},
        )
    sub.status = BillingSubscriptionStatus.PAST_DUE
    sub.grace_until = datetime.now(tz=timezone.utc) + timedelta(days=payload.grace_days)
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/mark_paid")
@audit_operation("mark_paid", "billing_subscription")
async def mark_paid(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> dict[str, str]:
    _ = access
    sub = (
        (
            await session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.tenant_id == tenant.id)
                .order_by(BillingSubscription.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if sub is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"},
        )
    sub.status = BillingSubscriptionStatus.ACTIVE
    sub.grace_until = None
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/suspend")
@audit_operation("suspend", "billing_subscription")
async def suspend(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> dict[str, str]:
    _ = access
    sub = (
        (
            await session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.tenant_id == tenant.id)
                .order_by(BillingSubscription.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if sub is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"},
        )
    sub.status = BillingSubscriptionStatus.SUSPENDED
    await session.commit()
    return {"status": "ok"}


@router.post("/subscription/activate")
@audit_operation("activate", "billing_subscription")
async def activate(
    session: SessionDep, access: OwnerAdminAccess, tenant: Tenant = Depends(get_tenant_record)
) -> dict[str, str]:
    _ = access
    sub = (
        (
            await session.execute(
                select(BillingSubscription)
                .where(BillingSubscription.tenant_id == tenant.id)
                .order_by(BillingSubscription.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if sub is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription not found"},
        )
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


# ---------------------------------------------------------------------------
# BIZ-52 разд. 52.4 (срез-189): цены партнёра для своих клиентов и его выручка.
# ---------------------------------------------------------------------------
#
# Цену партнёр назначает САМ (решение среза-8) — платформа её не диктует. Но
# хранить её было негде, и отчёт о выручке было не из чего считать.
#
# У цены есть СРОК ДЕЙСТВИЯ: перезаписываемая цена переписывает прошлое —
# подняли тариф в сентябре, и отчёт за июль показывает сентябрьскую сумму.
# Спорить с таким отчётом невозможно, а партнёр по нему выставляет счета.


class ResellerPriceUpsert(BaseModel):
    client_tenant_id: str = Field(min_length=1, max_length=36)
    #: Копейки. Дробные рубли в плавающей точке дают расхождение в итогах,
    #: которое невозможно объяснить.
    amount_minor: int = Field(ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    period: str = Field(default="month")
    valid_from: date
    valid_to: date | None = None
    note: str | None = Field(default=None, max_length=255)


class ResellerPriceRead(BaseModel):
    id: str
    client_tenant_id: str
    amount_minor: int
    currency: str
    period: str
    valid_from: date
    valid_to: date | None = None
    note: str | None = None


def _price_read(row: ResellerPrice) -> ResellerPriceRead:
    return ResellerPriceRead(
        id=str(row.id),
        client_tenant_id=str(row.client_tenant_id),
        amount_minor=int(row.amount_minor),
        currency=row.currency,
        period=row.period,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
        note=row.note,
    )


@router.get("/reseller/prices", response_model=list[ResellerPriceRead])
async def list_reseller_prices(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = Depends(
        abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")
    ),
) -> list[ResellerPriceRead]:
    rows = (
        (
            await session.execute(
                select(ResellerPrice)
                .where(ResellerPrice.reseller_tenant_id == str(tenant.id))
                .order_by(ResellerPrice.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_price_read(row) for row in rows]


@router.post("/reseller/prices", response_model=ResellerPriceRead, status_code=201)
@audit_operation("set_price", "reseller_price")
async def set_reseller_price(
    payload: ResellerPriceUpsert,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = Depends(
        abac(_tenant_resource_id, required_roles=["owner", "admin"], action="manage")
    ),
) -> ResellerPriceRead:
    """Назначить цену клиенту с даты. Прошлые строки НЕ переписываются."""

    if payload.period.lower() not in revenue.PERIOD_MONTHS:
        raise _billing_bad_request(
            "RESELLER_PRICE_BAD_PERIOD",
            f"Период должен быть одним из: {', '.join(sorted(revenue.PERIOD_MONTHS))}",
        )
    if payload.valid_to is not None and payload.valid_to < payload.valid_from:
        raise _billing_bad_request("RESELLER_PRICE_BAD_RANGE", "Дата окончания раньше даты начала")

    row = ResellerPrice(
        reseller_tenant_id=str(tenant.id),
        client_tenant_id=payload.client_tenant_id,
        amount_minor=payload.amount_minor,
        currency=payload.currency.upper(),
        period=payload.period.lower(),
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        note=payload.note,
    )
    session.add(row)
    await session.flush()
    return _price_read(row)


@router.get("/reseller/revenue")
async def reseller_revenue(
    session: SessionDep,
    since: date,
    until: date,
    currency: str = "RUB",
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = Depends(
        abac(_tenant_resource_id, required_roles=["owner", "admin"], action="read")
    ),
) -> dict:
    """Выручка партнёра за окно: складываются цены, действовавшие В НЁМ.

    Строки в другой валюте не складываются с запрошенной — но и не
    замалчиваются: партнёр решил бы, что клиента забыли завести.
    """

    if until < since:
        raise _billing_bad_request("RESELLER_REVENUE_BAD_RANGE", "Конец окна раньше начала")

    rows = (
        (
            await session.execute(
                select(ResellerPrice).where(ResellerPrice.reseller_tenant_id == str(tenant.id))
            )
        )
        .scalars()
        .all()
    )
    return revenue.build_report(rows, since=since, until=until, currency=currency)
