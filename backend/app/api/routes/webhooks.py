from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant, WebhookDelivery, WebhookSubscription
from app.services.webhooks import WebhookDispatcher

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]


class WebhookSubscriptionIn(BaseModel):
    event_type: str
    target_url: str
    secret: str | None = None
    headers: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class WebhookSubscriptionOut(WebhookSubscriptionIn):
    id: str


class WebhookDeliveryOut(BaseModel):
    id: str
    event_id: str
    subscription_id: str
    attempts: int
    status: str
    response_status: int | None = None
    last_error: dict[str, Any] | None = None


@router.get("/subscriptions", response_model=list[WebhookSubscriptionOut])
async def list_subscriptions(tenant: TenantDep, _: AdminAccess, session: SessionDep) -> list[WebhookSubscriptionOut]:
    rows = (
        await session.execute(
            select(WebhookSubscription).where(
                and_(
                    WebhookSubscription.tenant_id == tenant.id,
                )
            )
        )
    ).scalars().all()
    return [
        WebhookSubscriptionOut(
            id=row.id,
            event_type=row.event_type,
            target_url=row.url,
            secret=row.secret,
            headers=row.headers or {},
            is_enabled=row.enabled,
        )
        for row in rows
    ]


@router.post("/subscriptions", response_model=WebhookSubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(payload: WebhookSubscriptionIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookSubscriptionOut:
    existing = (
        await session.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.tenant_id == tenant.id,
                WebhookSubscription.event_type == payload.event_type,
                WebhookSubscription.url == payload.target_url,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "webhook_subscription_exists")
    row = WebhookSubscription(
        tenant_id=tenant.id,
        event_type=payload.event_type,
        url=payload.target_url,
        secret=payload.secret,
        headers=payload.headers,
        enabled=payload.is_enabled,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return WebhookSubscriptionOut(
        id=row.id,
        event_type=row.event_type,
        target_url=row.url,
        secret=row.secret,
        headers=row.headers or {},
        is_enabled=row.enabled,
    )


@router.patch("/subscriptions/{subscription_id}", response_model=WebhookSubscriptionOut)
async def update_subscription(subscription_id: str, payload: WebhookSubscriptionIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookSubscriptionOut:
    row = await session.get(WebhookSubscription, subscription_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_subscription_not_found")
    row.event_type = payload.event_type
    row.url = payload.target_url
    row.secret = payload.secret
    row.headers = payload.headers
    row.enabled = payload.is_enabled
    await session.commit()
    return WebhookSubscriptionOut(
        id=row.id,
        event_type=row.event_type,
        target_url=row.url,
        secret=row.secret,
        headers=row.headers or {},
        is_enabled=row.enabled,
    )


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    row = await session.get(WebhookSubscription, subscription_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_subscription_not_found")
    await session.delete(row)
    await session.commit()
    return {"status": "deleted"}


@router.post("/subscriptions/{subscription_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def send_test_event(subscription_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    row = await session.get(WebhookSubscription, subscription_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_subscription_not_found")
    dispatcher = WebhookDispatcher()
    payload = {"event_id": f"test-{subscription_id}", "correlation_id": "test-correlation"}
    await dispatcher.dispatch(
        event_type=row.event_type,
        tenant_id=str(tenant.id),
        payload=payload,
        destination=row.url,
        headers=row.headers or {},
        session=session,
    )
    return {"status": "queued"}


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[WebhookDeliveryOut]:
    stmt = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    rows = (await session.execute(stmt.order_by(WebhookDelivery.updated_at.desc()))).scalars().all()
    return [
        WebhookDeliveryOut(
            id=row.id,
            event_id=row.event_id,
            subscription_id=row.subscription_id,
            attempts=row.attempts,
            status=row.status,
            response_status=row.last_status_code,
            last_error=row.last_error,
        )
        for row in rows
    ]
