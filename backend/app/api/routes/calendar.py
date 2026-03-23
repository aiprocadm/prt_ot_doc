from __future__ import annotations

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import CalendarEvent, Tenant
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/calendar", tags=["calendar"])
_AuthDep = Depends(rbac())


@router.get("/events")
async def list_events(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session), _: AccessContext = _AuthDep):
    items = (await session.execute(select(CalendarEvent).where(CalendarEvent.tenant_id == tenant.id).order_by(CalendarEvent.starts_at.asc()))).scalars().all()
    return {"items": items, "total": len(items)}
