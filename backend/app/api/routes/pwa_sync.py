from __future__ import annotations

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import (
    BriefingJournal,
    BriefingTemplate,
    ComplianceDeadline,
    OfflineMediaQueue,
    OfflineSyncBatch,
    Tenant,
    TrainingEnrollment,
)
from app.modules.pwa_sync.services import OfflineSyncService
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/pwa", tags=["pwa"])


@router.post("/sync/batch")
async def create_batch(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    batch = OfflineSyncBatch(tenant_id=tenant.id, **payload)
    session.add(batch)
    await session.flush()
    return await OfflineSyncService().apply_batch(session, batch)


@router.get("/sync/status/{batch_id}")
async def sync_status(batch_id: str, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    batch = await OfflineSyncService().get_status(session, batch_id)
    if not batch or batch.tenant_id != tenant.id:
        raise HTTPException(404, "Batch not found")
    return batch


@router.post("/media/commit")
async def commit_media(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    media = OfflineMediaQueue(tenant_id=tenant.id, **payload)
    session.add(media)
    await session.flush()
    return await OfflineSyncService().commit_media(session, media)


@router.get("/bootstrap")
async def bootstrap(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    templates = (await session.execute(select(BriefingTemplate).where(BriefingTemplate.tenant_id == tenant.id, BriefingTemplate.deleted_at.is_(None), BriefingTemplate.status == "active"))).scalars().all()
    journals = (await session.execute(select(BriefingJournal).where(BriefingJournal.tenant_id == tenant.id, BriefingJournal.deleted_at.is_(None), BriefingJournal.status == "active"))).scalars().all()
    enrollments = (await session.execute(select(TrainingEnrollment).where(TrainingEnrollment.tenant_id == tenant.id, TrainingEnrollment.deleted_at.is_(None), TrainingEnrollment.status.in_(["assigned", "in_progress"])))).scalars().all()
    deadlines = (await session.execute(select(ComplianceDeadline).where(ComplianceDeadline.tenant_id == tenant.id, ComplianceDeadline.status.in_(["upcoming", "due", "overdue"])))).scalars().all()
    return {
        "current_user": {"id": None},
        "tenant_branding": {"slug": tenant.slug, "name": tenant.name},
        "route_permissions": [],
        "briefing_templates": templates,
        "active_journals": journals,
        "assigned_training": enrollments,
        "compliance_deadlines_summary": {"count": len(deadlines)},
        "dictionaries": {},
    }
