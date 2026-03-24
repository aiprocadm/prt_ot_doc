"""Realtime events fallback endpoints.

WebSocket transport is still pending, but this route now provides a production-safe
polling fallback backed by internal outbox projections.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Outbox, Tenant
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class WsEventItem(BaseModel):
    id: str
    event_type: str
    status: str
    destination: str
    attempts: int
    created_at: datetime | None = None
    payload_keys: list[str] = Field(default_factory=list)


class WsEventsFallbackResponse(BaseModel):
    transport_mode: str
    provider_mode: str
    websocket_available: bool
    polling_interval_seconds: int
    generated_at: datetime
    count: int
    items: list[WsEventItem] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


@router.get("/ws/v1/events")
async def ws_events_stub(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    limit: int = Query(50, ge=1, le=200),
    since: datetime | None = Query(default=None),
) -> WsEventsFallbackResponse:
    stmt = select(Outbox).where(Outbox.tenant_id == str(tenant.id))
    if since is not None:
        stmt = stmt.where(Outbox.created_at >= since)

    rows = (
        await session.execute(
            stmt.order_by(Outbox.created_at.desc()).limit(limit)
        )
    ).scalars().all()

    items = [
        WsEventItem(
            id=str(row.id),
            event_type=row.event_type,
            status=getattr(row.status, "value", str(row.status)),
            destination=row.destination,
            attempts=int(row.attempts or 0),
            created_at=row.created_at,
            payload_keys=sorted((row.payload or {}).keys()) if isinstance(row.payload, dict) else [],
        )
        for row in rows
    ]

    return WsEventsFallbackResponse(
        transport_mode="polling_fallback",
        provider_mode="non_production",
        websocket_available=False,
        polling_interval_seconds=5,
        generated_at=datetime.now(timezone.utc),
        count=len(items),
        items=items,
        diagnostics={
            "reason": "websocket_transport_pending",
            "source": "outbox_projection",
            "tenant_scoped": True,
        },
    )
