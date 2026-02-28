from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.models.models import Tenant
from app.modules.files import service
from app.modules.files.models import FileLink, FileRecord
from app.modules.files.schemas import (
    DownloadURLResponse,
    DownloadUrlRequest,
    DownloadUrlResponse,
    EntityFileListItem,
    FileDto,
    FinalizeUploadResponse,
    LinkFileRequest,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadSessionRequest,
    UploadSessionResponse,
)
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter()


@router.post(":upload-init", response_model=UploadInitResponse)
async def upload_init(
    payload: UploadInitRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> UploadInitResponse:
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
    request_hash = compute_request_hash(payload.model_dump(mode="json"))
    idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="files.upload_init")
    key = normalize_idempotency_key(idempotency_key)
    record, created = await idem.acquire(
        key=key,
        request_hash=request_hash,
        method="POST",
        path="/v1/files:upload-init",
    )
    if not created:
        return await idem.respond_from_store(record, model=UploadInitResponse, response=response)

    obj, version, url = await service.create_upload_session(session=session, tenant_id=str(tenant.id), payload=payload, user_id=None)
    body = UploadInitResponse(file_id=obj.id, version_id=version.id, upload_url=url, s3_key=version.s3_key)
    await idem.store_success(record, status_code=status.HTTP_200_OK, body=body.model_dump())
    await session.commit()
    return body


@router.post(":upload-complete", response_model=UploadCompleteResponse)
async def upload_complete(
    payload: UploadCompleteRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> UploadCompleteResponse:
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
    request_hash = compute_request_hash(payload.model_dump(mode="json"))
    idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint="files.upload_complete")
    key = normalize_idempotency_key(idempotency_key)
    record, created = await idem.acquire(
        key=key,
        request_hash=request_hash,
        method="POST",
        path="/v1/files:upload-complete",
    )
    if not created:
        return await idem.respond_from_store(record, model=UploadCompleteResponse, response=response)

    version = await service.complete_upload(session=session, tenant_id=str(tenant.id), file_id=payload.file_id, version_id=payload.version_id)
    body = {"version_id": version.id, "status": version.status, "av_status": version.av_status}
    await idem.store_success(record, status_code=status.HTTP_200_OK, body=body)
    await session.commit()
    return UploadCompleteResponse(**body)


@router.get("/{file_id}/versions/{version_id}:download-url", response_model=DownloadURLResponse)
async def download_url(file_id: str, version_id: str, request: Request, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> DownloadURLResponse:
    url = await service.issue_download_url(
        session=session,
        tenant_id=str(tenant.id),
        file_id=file_id,
        version_id=version_id,
        user_id=None,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return DownloadURLResponse(url=url, expires_in=600)


@router.post(":upload-session", response_model=UploadSessionResponse)
async def create_upload_session_v2(
    payload: UploadSessionRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> UploadSessionResponse:
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    file_record, upload_url, expires_in = await svc.create_upload_session(
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        metadata_json=payload.metadata_json,
    )
    await session.commit()
    return UploadSessionResponse(file_id=file_record.id, upload_url=upload_url, expires_in=expires_in)


@router.post("/{file_id}:complete", response_model=FinalizeUploadResponse)
async def finalize_upload_v2(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> FinalizeUploadResponse:
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    file_record = await svc.finalize_upload(file_id=file_id)
    await session.commit()
    return FinalizeUploadResponse(file_id=file_record.id, status=file_record.status)


@router.get("/{file_id}", response_model=FileDto)
async def get_file_v2(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> FileDto:
    file_record = await session.get(FileRecord, file_id)
    if file_record is None or file_record.tenant_id != str(tenant.id):
        raise HTTPException(status_code=404, detail="file_not_found")
    return FileDto(
        id=file_record.id,
        bucket=file_record.bucket,
        object_key=file_record.object_key,
        content_type=file_record.content_type,
        size_bytes=file_record.size_bytes,
        sha256=file_record.sha256,
        status=file_record.status,
        av_vendor=file_record.av_vendor,
        av_result_json=file_record.av_result_json or {},
        metadata_json=file_record.metadata_json or {},
    )


@router.post("/{file_id}:download-url", response_model=DownloadUrlResponse)
async def get_download_url_v2(
    file_id: str,
    payload: DownloadUrlRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> DownloadUrlResponse:
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    url = await svc.get_signed_download_url(
        file_id=file_id,
        purpose=payload.purpose,
        ttl=payload.ttl_seconds,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return DownloadUrlResponse(signed_get_url=url)


@router.post("/{file_id}:link")
async def link_file_v2(
    file_id: str,
    payload: LinkFileRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> None:
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    await svc.link_file(file_id=file_id, entity_type=payload.entity_type, entity_id=payload.entity_id, role=payload.role)
    await session.commit()


@router.get("/entities/{entity_type}/{entity_id}/list", response_model=list[EntityFileListItem])
async def list_entity_files_v2(
    entity_type: str,
    entity_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> list[EntityFileListItem]:
    rows = (
        await session.execute(
            select(FileLink, FileRecord)
            .join(FileRecord, FileRecord.id == FileLink.file_id)
            .where(
                FileLink.tenant_id == str(tenant.id),
                FileLink.entity_type == entity_type,
                FileLink.entity_id == entity_id,
            )
        )
    ).all()
    return [
        EntityFileListItem(
            file_id=file_rec.id,
            role=link.role,
            status=file_rec.status,
            display_name=Path(file_rec.object_key).name,
            size=file_rec.size_bytes,
        )
        for link, file_rec in rows
    ]
