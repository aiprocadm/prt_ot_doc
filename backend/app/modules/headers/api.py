from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.document import DocumentVersion
from app.models.job_engine import DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus
from app.models.models import Tenant
from app.modules.headers.models import HeaderFooterPreset
from app.modules.headers.schemas import (
    ApplyHeadersAccepted,
    ApplyHeadersRequest,
    HeaderFooterPresetCreate,
    HeaderFooterPresetPatch,
    HeaderFooterPresetRead,
    LayoutPresetList,
)
from app.services.billing import BillingService
from app.services.celery_app import celery_app
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter()


@router.post("/layout-presets", response_model=HeaderFooterPresetRead, status_code=status.HTTP_201_CREATED)
async def create_layout_preset(
    payload: HeaderFooterPresetCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> HeaderFooterPresetRead:
    _ = access
    record = HeaderFooterPreset(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return HeaderFooterPresetRead.model_validate(record)


@router.get("/layout-presets", response_model=LayoutPresetList)
async def list_layout_presets(
    search: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> LayoutPresetList:
    _ = access
    stmt = select(HeaderFooterPreset).where(HeaderFooterPreset.tenant_id == str(tenant.id), HeaderFooterPreset.deleted_at.is_(None)).order_by(HeaderFooterPreset.updated_at.desc())
    if search:
        stmt = stmt.where(HeaderFooterPreset.name.ilike(f"%{search}%"))
    rows = (await session.execute(stmt)).scalars().all()
    return LayoutPresetList(items=[HeaderFooterPresetRead.model_validate(x) for x in rows])


@router.get("/layout-presets/{preset_id}", response_model=HeaderFooterPresetRead)
async def get_layout_preset(
    preset_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> HeaderFooterPresetRead:
    _ = access
    row = await session.get(HeaderFooterPreset, preset_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    return HeaderFooterPresetRead.model_validate(row)


@router.patch("/layout-presets/{preset_id}", response_model=HeaderFooterPresetRead)
async def patch_layout_preset(
    preset_id: str,
    payload: HeaderFooterPresetPatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> HeaderFooterPresetRead:
    _ = access
    row = await session.get(HeaderFooterPreset, preset_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return HeaderFooterPresetRead.model_validate(row)


@router.delete("/layout-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_layout_preset(
    preset_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> None:
    _ = access
    row = await session.get(HeaderFooterPreset, preset_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preset not found")
    row.deleted_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_version_id}/apply-headers", response_model=ApplyHeadersAccepted)
async def apply_headers(
    document_version_id: str,
    payload: ApplyHeadersRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> ApplyHeadersAccepted:
    _ = access
    await BillingService(session).assert_allowed(tenant, "documents.generate")
    key = normalize_idempotency_key(idempotency_key)
    version = await session.get(DocumentVersion, document_version_id)
    if version is None or version.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")

    service = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="documents.apply_headers")
    request_hash = hashlib.sha256(json.dumps(payload.model_dump(), sort_keys=True).encode("utf-8")).hexdigest()
    record, created = await service.acquire(key=key, request_hash=request_hash, method="POST", path=f"/documents/{document_version_id}/apply-headers")
    if not created and record.status.value == "succeeded":
        return await service.respond_from_store(record, model=ApplyHeadersAccepted)

    job = DocumentJob(
        tenant_id=str(tenant.id),
        kind="apply_headers",
        status=DocumentJobStatus.QUEUED.value,
        pipeline_profile_id=None,
        preset_id=None,
        input_sha256="-",
        request_hash=request_hash,
        idempotency_key=key,
        template_code="apply_headers",
        template_version=None,
        correlation_id=f"apply_headers:{document_version_id}:{payload.preset_code}",
    )
    session.add(job)
    await session.flush()
    session.add(DocumentJobStep(tenant_id=str(tenant.id), job_id=job.id, step_code="apply_headers", status=JobStepStatus.QUEUED.value, input_ref={"document_version_id": document_version_id, "preset_code": payload.preset_code, "context": payload.data or {}, "watermark_override": payload.watermark_override}))
    await session.flush()

    celery_app.send_task("app.tasks.apply_headers_job", kwargs={"job_id": job.id, "tenant_slug": tenant.slug})
    result = ApplyHeadersAccepted(job_id=job.id)
    await service.store_success(record, status_code=202, body=result.model_dump())
    await session.commit()
    return result
