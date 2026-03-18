from __future__ import annotations

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.export_center.service import ExportCenterService
from app.modules.projections.models import ExportJob, ExportSchedule, KpiDefinition
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/exports", tags=["exports"])


class ExportCreate(BaseModel):
    export_type: str
    dataset_code: str | None = None
    schema_version: str = "v1"
    anonymized: bool = False
    target_type: str = "file"
    target_config: dict = Field(default_factory=dict)
    scope_json: dict = Field(default_factory=dict)
    filters_json: dict = Field(default_factory=dict)


class ExportScheduleCreate(BaseModel):
    name: str
    dataset_code: str
    schema_version: str = "v1"
    cron_expr: str
    anonymized: bool = False
    target_type: str = "file"
    target_config: dict = Field(default_factory=dict)
    filters_json: dict = Field(default_factory=dict)


class KpiDefinitionCreate(BaseModel):
    code: str
    name: str
    dataset_code: str
    formula_json: dict = Field(default_factory=dict)
    threshold_json: dict = Field(default_factory=dict)
    locale_labels: dict = Field(default_factory=dict)


@router.get("")
async def list_exports(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(ExportJob).where(ExportJob.tenant_id == str(tenant.id)).order_by(ExportJob.updated_at.desc()))).scalars().all()
    return rows


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_export(
    payload: ExportCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    service = ExportCenterService(session, str(tenant.id))
    return await service.create_job(
        export_type=payload.export_type,
        dataset_code=payload.dataset_code,
        schema_version=payload.schema_version,
        anonymized=payload.anonymized,
        target_type=payload.target_type,
        target_config=payload.target_config,
        scope_json=payload.scope_json,
        filters_json=payload.filters_json,
        idempotency_key=idempotency_key,
    )


@router.get("/schedules")
async def list_schedules(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(ExportSchedule).where(ExportSchedule.tenant_id == str(tenant.id)).order_by(ExportSchedule.updated_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(payload: ExportScheduleCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    return await ExportCenterService(session, str(tenant.id)).create_schedule_with_schema(
        name=payload.name,
        dataset_code=payload.dataset_code,
        schema_version=payload.schema_version,
        cron_expr=payload.cron_expr,
        filters_json=payload.filters_json,
        anonymized=payload.anonymized,
        target_type=payload.target_type,
        target_config=payload.target_config,
    )


@router.get("/kpis")
async def list_kpis(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(KpiDefinition).where(KpiDefinition.tenant_id == str(tenant.id)).order_by(KpiDefinition.updated_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.post("/kpis", status_code=status.HTTP_201_CREATED)
async def create_kpi(payload: KpiDefinitionCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    return await ExportCenterService(session, str(tenant.id)).create_kpi_definition(
        code=payload.code,
        name=payload.name,
        dataset_code=payload.dataset_code,
        formula_json=payload.formula_json,
        threshold_json=payload.threshold_json,
        locale_labels=payload.locale_labels,
    )


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
