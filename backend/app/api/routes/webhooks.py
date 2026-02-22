from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant, WebhookDelivery, WebhookEndpoint

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]


class WebhookEndpointIn(BaseModel):
    url: str
    secret: str | None = None
    is_enabled: bool = True
    subscribed_events: list[str] = Field(default_factory=list)
    headers: dict[str, Any] = Field(default_factory=dict)


class WebhookEndpointOut(WebhookEndpointIn):
    id: str


class WebhookDeliveryOut(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    attempts: int
    status: str
    response_status: int | None = None
    last_response_body: str | None = None
    last_error: dict[str, Any] | None = None


@router.get("", response_model=list[WebhookEndpointOut])
async def list_webhooks(tenant: TenantDep, _: AdminAccess, session: SessionDep) -> list[WebhookEndpointOut]:
    rows = (await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant.id))).scalars().all()
    return [WebhookEndpointOut(id=row.id, url=row.url, secret=row.secret, is_enabled=row.is_enabled, subscribed_events=row.subscribed_events or [], headers=row.headers or {}) for row in rows]


@router.post("", response_model=WebhookEndpointOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(payload: WebhookEndpointIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    row = WebhookEndpoint(tenant_id=tenant.id, url=payload.url, secret=payload.secret, is_enabled=payload.is_enabled, subscribed_events=payload.subscribed_events, headers=payload.headers)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return WebhookEndpointOut(id=row.id, url=row.url, secret=row.secret, is_enabled=row.is_enabled, subscribed_events=row.subscribed_events or [], headers=row.headers or {})


@router.patch("/{webhook_id}", response_model=WebhookEndpointOut)
async def update_webhook(webhook_id: str, payload: WebhookEndpointIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    row.url = payload.url
    row.secret = payload.secret
    row.is_enabled = payload.is_enabled
    row.subscribed_events = payload.subscribed_events
    row.headers = payload.headers
    await session.commit()
    return WebhookEndpointOut(id=row.id, url=row.url, secret=row.secret, is_enabled=row.is_enabled, subscribed_events=row.subscribed_events or [], headers=row.headers or {})


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    await session.delete(row)
    await session.commit()
    return {"status": "deleted"}


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(tenant: TenantDep, _: AdminAccess, session: SessionDep, status_filter: str | None = Query(default=None, alias="status")) -> list[WebhookDeliveryOut]:
    stmt = select(WebhookDelivery).where(WebhookDelivery.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    rows = (await session.execute(stmt.order_by(WebhookDelivery.updated_at.desc()))).scalars().all()
    return [WebhookDeliveryOut(id=row.id, event_id=row.event_id, endpoint_id=row.endpoint_id, attempts=row.attempts, status=row.status, response_status=row.last_status_code, last_response_body=row.last_response_body, last_error=row.last_error) for row in rows]
