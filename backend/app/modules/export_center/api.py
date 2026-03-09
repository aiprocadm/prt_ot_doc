from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.projections.models import ExportJob

router = APIRouter(prefix="/exports", tags=["exports"])


class ExportCreate(BaseModel):
    export_type: str
    scope_json: dict = Field(default_factory=dict)
    filters_json: dict = Field(default_factory=dict)


@router.get("")
async def list_exports(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(ExportJob).where(ExportJob.tenant_id == str(tenant.id)).order_by(ExportJob.updated_at.desc()))).scalars().all()
    return rows


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_export(payload: ExportCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    job = ExportJob(tenant_id=str(tenant.id), export_type=payload.export_type, scope_json=payload.scope_json, filters_json=payload.filters_json, status="queued")
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@router.get("/{job_id}")
async def get_export(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    job = (await session.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == str(tenant.id)))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export job not found")
    return job


@router.post("/{job_id}/retry")
async def retry_export(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    job = (await session.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == str(tenant.id)))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export job not found")
    job.status = "queued"
    await session.commit()
    return {"status": "queued", "id": job.id}


@router.get("/{job_id}/download-link")
async def export_download_link(job_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    job = (await session.execute(select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == str(tenant.id)))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Export job not found")
    if not job.file_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Export file not ready")
    return {"download_url": f"/api/v1/files/{job.file_id}/download", "expires_in": 300}
