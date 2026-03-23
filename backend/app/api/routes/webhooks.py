from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, rbac
from app.models.job_engine import InboundWebhookDedup
from app.models.models import Outbox, OutboxStatus, Tenant, WebhookDelivery, WebhookEndpoint
from app.tasks import compute_inbound_dedup_key, process_inbound_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin", "owner", "integrations"]))]


class WebhookEndpointIn(BaseModel):
    name: str | None = None
    url: str
    secret: str | None = None
    enabled: bool = True
    subscribed_events: list[str] = Field(default_factory=list)
    timeout_ms: int = 5000
    headers: dict[str, Any] = Field(default_factory=dict)


class WebhookEndpointOut(BaseModel):
    id: str
    name: str | None = None
    url: str
    secret_masked: str | None = None
    enabled: bool
    subscribed_events: list[str]
    timeout_ms: int
    headers: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WebhookEndpointCreateOut(WebhookEndpointOut):
    secret: str | None = None


class WebhookDeliveryOut(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    attempts: int
    status: str
    next_attempt_at: datetime | None = None
    response_status: int | None = None
    last_response_body: str | None = None
    last_error: dict[str, Any] | None = None
    latency_ms: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}***{secret[-2:]}"


def _to_endpoint_out(row: WebhookEndpoint) -> WebhookEndpointOut:
    return WebhookEndpointOut(
        id=row.id,
        name=row.name,
        url=row.url,
        secret_masked=_mask_secret(row.secret),
        enabled=row.is_enabled,
        subscribed_events=row.subscribed_events or [],
        timeout_ms=row.timeout_ms,
        headers=row.headers or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/endpoints", response_model=list[WebhookEndpointOut])
async def list_webhooks(tenant: TenantDep, _: AdminAccess, session: SessionDep) -> list[WebhookEndpointOut]:
    rows = (
        await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant.id).order_by(WebhookEndpoint.created_at.desc()))
    ).scalars().all()
    return [_to_endpoint_out(row) for row in rows]


@router.post("/endpoints", response_model=WebhookEndpointCreateOut, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "webhook_endpoint")
async def create_webhook(payload: WebhookEndpointIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    generated_secret = payload.secret or secrets.token_urlsafe(32)
    row = WebhookEndpoint(
        tenant_id=tenant.id,
        name=payload.name,
        url=payload.url,
        secret=generated_secret,
        is_enabled=payload.enabled,
        subscribed_events=payload.subscribed_events,
        timeout_ms=payload.timeout_ms,
        headers=payload.headers,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return WebhookEndpointCreateOut(**_to_endpoint_out(row).model_dump(), secret=generated_secret)


@router.patch("/endpoints/{webhook_id}", response_model=WebhookEndpointOut)
@audit_operation("update", "webhook_endpoint")
async def update_webhook(webhook_id: str, payload: WebhookEndpointIn, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    row.name = payload.name
    row.url = payload.url
    row.secret = payload.secret
    row.is_enabled = payload.enabled
    row.subscribed_events = payload.subscribed_events
    row.timeout_ms = payload.timeout_ms
    row.headers = payload.headers
    await session.commit()
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.delete("/endpoints/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "webhook_endpoint")
async def delete_webhook(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> None:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    await session.delete(row)
    await session.commit()


@router.post("/endpoints/{webhook_id}:rotate-secret", response_model=WebhookEndpointCreateOut)
@audit_operation("rotate_secret", "webhook_endpoint")
async def rotate_webhook_secret(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointCreateOut:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    new_secret = secrets.token_urlsafe(32)
    row.secret = new_secret
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return WebhookEndpointCreateOut(**_to_endpoint_out(row).model_dump(), secret=new_secret)


@router.post("/endpoints/{webhook_id}:disable", response_model=WebhookEndpointOut)
@audit_operation("disable", "webhook_endpoint")
async def disable_webhook(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    row.is_enabled = False
    await session.commit()
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.post("/endpoints/{webhook_id}:enable", response_model=WebhookEndpointOut)
@audit_operation("enable", "webhook_endpoint")
async def enable_webhook(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> WebhookEndpointOut:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    row.is_enabled = True
    await session.commit()
    await session.refresh(row)
    return _to_endpoint_out(row)


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
async def list_deliveries(
    tenant: TenantDep,
    _: AdminAccess,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
    endpoint_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
) -> list[WebhookDeliveryOut]:
    stmt = select(WebhookDelivery, Outbox.event_type).join(Outbox, Outbox.id == WebhookDelivery.event_id).where(WebhookDelivery.tenant_id == tenant.id)
    if status_filter:
        stmt = stmt.where(WebhookDelivery.status == status_filter)
    if endpoint_id:
        stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
    if event_type:
        stmt = stmt.where(Outbox.event_type == event_type)
    rows = (await session.execute(stmt.order_by(WebhookDelivery.updated_at.desc()))).all()
    return [
        WebhookDeliveryOut(
            id=delivery.id,
            event_id=delivery.event_id,
            endpoint_id=delivery.endpoint_id,
            attempts=delivery.attempts,
            status=delivery.status,
            next_attempt_at=delivery.next_attempt_at,
            response_status=delivery.last_status_code,
            last_response_body=delivery.last_response_body,
            last_error=delivery.last_error,
            latency_ms=delivery.latency_ms,
            started_at=delivery.started_at,
            ended_at=delivery.ended_at,
        )
        for delivery, _ in rows
    ]


@router.get("/endpoints/{webhook_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_endpoint_deliveries(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> list[WebhookDeliveryOut]:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    rows = (
        await session.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.tenant_id == tenant.id,
                WebhookDelivery.endpoint_id == webhook_id,
            ).order_by(WebhookDelivery.created_at.desc())
        )
    ).scalars().all()
    return [
        WebhookDeliveryOut(
            id=delivery.id,
            event_id=delivery.event_id,
            endpoint_id=delivery.endpoint_id,
            attempts=delivery.attempts,
            status=delivery.status,
            next_attempt_at=delivery.next_attempt_at,
            response_status=delivery.last_status_code,
            last_response_body=delivery.last_response_body,
            last_error=delivery.last_error,
            latency_ms=delivery.latency_ms,
            started_at=delivery.started_at,
            ended_at=delivery.ended_at,
        )
        for delivery in rows
    ]


@router.post("/endpoints/{webhook_id}:test")
@audit_operation("test", "webhook_endpoint")
async def test_endpoint(webhook_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    row = await session.get(WebhookEndpoint, webhook_id)
    if row is None or row.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "webhook_not_found")
    event = Outbox(
        tenant_id=str(tenant.id),
        event_type="DocumentGenerated",
        destination=row.url,
        payload={"tenant_id": str(tenant.id), "event_id": f"test-{webhook_id}", "document_id": "test", "document_version_id": "test", "template_id": "test", "template_version_id": "test", "company_id": "test", "status": "generated"},
        headers={"X-Webhook-Endpoint-Id": row.id, "X-Correlation-Id": f"test-{webhook_id}"},
        idempotency_key=f"webhook-test:{webhook_id}:{datetime.now(timezone.utc).timestamp()}",
        status=OutboxStatus.PENDING,
        next_attempt_at=datetime.now(tz=timezone.utc),
    )
    session.add(event)
    await session.commit()
    return {"status": "queued"}


@router.post("/deliveries/{delivery_id}:retry")
@audit_operation("retry", "webhook_delivery")
async def retry_delivery(delivery_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None or delivery.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "delivery_not_found")
    delivery.status = "pending"
    delivery.next_attempt_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "queued"}


@router.post("/events/{event_id}:replay")
@audit_operation("replay", "outbox_event")
async def replay_event(event_id: str, tenant: TenantDep, _: AdminAccess, session: SessionDep) -> dict[str, str]:
    event = await session.get(Outbox, event_id)
    if event is None or event.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "event_not_found")
    event.status = OutboxStatus.PENDING
    event.next_attempt_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "queued"}


@router.post("/inbound/{source}", status_code=status.HTTP_202_ACCEPTED)
@audit_operation("inbound", "webhook_event")
async def inbound_webhook(
    source: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
) -> dict[str, str]:
    raw = await request.body()
    payload = await request.json()
    dedup_key = compute_inbound_dedup_key(payload, raw)
    row = InboundWebhookDedup(
        tenant_id=tenant.id,
        source=source,
        dedup_key=dedup_key,
        payload_hash=__import__("hashlib").sha256(raw).hexdigest(),
        received_at=datetime.now(timezone.utc),
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate"}
    process_inbound_webhook.delay(source=source, tenant_slug=tenant.slug, payload=payload)
    return {"status": "accepted"}
