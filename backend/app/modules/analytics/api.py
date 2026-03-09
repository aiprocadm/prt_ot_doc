from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.projections.models import DashboardKpiSnapshot
from app.modules.projections.services import ProjectionOrchestrator

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard/executive")
async def executive_dashboard(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict:
    today = date.today()
    snapshot = (
        await session.execute(
            select(DashboardKpiSnapshot).where(
                DashboardKpiSnapshot.tenant_id == str(tenant.id),
                DashboardKpiSnapshot.scope_type == "tenant",
                DashboardKpiSnapshot.snapshot_date == today,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_dashboard_snapshot(today)
    return {"snapshot_date": today, "widgets": snapshot.payload}


@router.post("/recompute")
async def recompute_dashboard(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict:
    snapshot = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_dashboard_snapshot(date.today())
    return {"status": "ok", "payload": snapshot.payload}
