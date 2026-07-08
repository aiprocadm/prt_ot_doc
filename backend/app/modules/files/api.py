from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.upload import reject_oversize_upload
from app.api.tenant_row_http import enforce_row_belongs_to_tenant
from app.core.idempotency import compute_request_hash
from app.core.security import AccessContext, abac
from app.models.models import Tenant
from app.modules.files import service
from app.modules.files.models import FileContentIndex, FileLink, FileRecord, FileVersion
from app.modules.files.schemas import (
    CompleteUploadRequest,
    DownloadUrlRequest,
    DownloadURLResponse,
    DownloadUrlResponse,
    EntityFileListItem,
    FileDto,
    FileIndexStatusDto,
    FileVersionDto,
    FinalizeUploadResponse,
    LinkFileRequest,
    LinkFileResponse,
    NewFileVersionRequest,
    NewFileVersionResponse,
    ReindexFileResponse,
    SignedUrlRequest,
    SignedUrlResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitRequest,
    UploadInitResponse,
    UploadSessionRequest,
    UploadSessionResponse,
)
from app.services.billing import BillingService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter()

# Canonical files API router for `/api/v1/files` endpoints.
_FILE_UPLOAD_ROLES = ["admin", "employee"]
_FILE_READ_ROLES = ["admin", "employee", "client_admin", "client_user"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return str(getattr(tenant, "id", "")) or None


WRITE_ACCESS_DEP = Depends(
    abac(_tenant_resource_id, required_roles=_FILE_UPLOAD_ROLES, action="write files")
)
READ_ACCESS_DEP = Depends(
    abac(_tenant_resource_id, required_roles=_FILE_READ_ROLES, action="read files")
)


def _enforce_access_role(access: AccessContext, allowed_roles: list[str]) -> None:
    if access.role not in set(allowed_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role")


@router.post(
    ":upload-init",
    response_model=UploadInitResponse,
    operation_id="files_upload_init",
)
async def upload_init(
    payload: UploadInitRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> UploadInitResponse:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
    request_hash = compute_request_hash(payload.model_dump(mode="json"))
    idem = IdempotencyService(
        session=session, tenant_id=str(tenant.id), endpoint="files.upload_init"
    )
    key = normalize_idempotency_key(idempotency_key)
    record, created = await idem.acquire(
        key=key,
        request_hash=request_hash,
        method="POST",
        path="/v1/files:upload-init",
    )
    if not created:
        return await idem.respond_from_store(record, model=UploadInitResponse, response=response)

    obj, version, url = await service.create_upload_session(
        session=session,
        tenant_id=str(tenant.id),
        payload=payload,
        user_id=getattr(access.user, "id", None),
    )
    body = UploadInitResponse(
        file_id=obj.id,
        version_id=version.id,
        upload_url=url,
        s3_key=version.s3_key,
    )
    await idem.store_success(record, status_code=status.HTTP_200_OK, body=body.model_dump())
    await session.commit()
    return body


@router.post(
    ":upload-complete",
    response_model=UploadCompleteResponse,
    operation_id="files_upload_complete",
)
async def upload_complete(
    payload: UploadCompleteRequest,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> UploadCompleteResponse:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    if not idempotency_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Idempotency-Key is required")
    request_hash = compute_request_hash(payload.model_dump(mode="json"))
    idem = IdempotencyService(
        session=session, tenant_id=str(tenant.id), endpoint="files.upload_complete"
    )
    key = normalize_idempotency_key(idempotency_key)
    record, created = await idem.acquire(
        key=key,
        request_hash=request_hash,
        method="POST",
        path="/v1/files:upload-complete",
    )
    if not created:
        return await idem.respond_from_store(
            record, model=UploadCompleteResponse, response=response
        )

    version = await service.complete_upload(
        session=session,
        tenant_id=str(tenant.id),
        file_id=payload.file_id,
        version_id=payload.version_id,
    )
    body = {"version_id": version.id, "status": version.status, "av_status": version.av_status}
    await idem.store_success(record, status_code=status.HTTP_200_OK, body=body)
    await session.commit()
    return UploadCompleteResponse(**body)


@router.get(
    "/{file_id}/versions/{version_id}:download-url",
    response_model=DownloadURLResponse,
    operation_id="files_version_download_url",
)
async def download_url(
    file_id: str,
    version_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> DownloadURLResponse:
    url = await service.issue_download_url(
        session=session,
        tenant_id=str(tenant.id),
        file_id=file_id,
        version_id=version_id,
        user_id=getattr(access.user, "id", None),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    return DownloadURLResponse(url=url, expires_in=600)


@router.post(
    "/presign-upload",
    response_model=UploadSessionResponse,
    operation_id="files_presign_upload",
)
@router.post(
    "/init-upload",
    response_model=UploadSessionResponse,
    operation_id="files_init_upload_legacy_compat",
)
async def create_upload_session_v2(
    payload: UploadSessionRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> UploadSessionResponse:
    """Create upload session.

    Canonical path: `/api/v1/files/presign-upload`.
    Legacy-compat alias: `/api/v1/files/init-upload`.
    """
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    await BillingService(session).assert_allowed(
        tenant,
        "files.upload",
        meta={"delta_bytes": int(payload.size_bytes)},
    )
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    file_record, upload_url, expires_in = await svc.create_upload_session(
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        metadata_json=payload.metadata
        or payload.metadata_json
        or ({"sha256": payload.sha256} if payload.sha256 else None),
    )
    await session.commit()
    return UploadSessionResponse(
        file_id=file_record.id,
        signed_put_url=upload_url,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=max(expires_in, 0)),
        existing=(upload_url == ""),
    )


@router.post(
    "/complete-upload",
    response_model=FinalizeUploadResponse,
    operation_id="files_complete_upload",
)
@router.post(
    "/complete-upload-v2",
    response_model=FinalizeUploadResponse,
    operation_id="files_complete_upload_v2_legacy_compat",
)
async def complete_upload_v2(
    payload: CompleteUploadRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> FinalizeUploadResponse:
    """Finalize upload.

    Canonical path: `/api/v1/files/complete-upload`.
    Legacy-compat alias: `/api/v1/files/complete-upload-v2`.
    """
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    file_record = await svc.finalize_upload(
        file_id=payload.file_id,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
    )
    await BillingService(session).add_usage(
        tenant_id=str(tenant.id),
        s3_bytes_delta=int(file_record.size_bytes or 0),
        ref_id=file_record.id,
    )
    await session.commit()
    return FinalizeUploadResponse(file_id=file_record.id, status=file_record.status)


@router.post(
    "/{file_id}:finalize",
    response_model=FinalizeUploadResponse,
    operation_id="files_finalize_upload",
)
@router.post(
    "/{file_id}:complete",
    response_model=FinalizeUploadResponse,
    operation_id="files_complete_file_upload_legacy_compat",
)
async def finalize_upload_v2(
    file_id: str,
    payload: UploadCompleteRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> FinalizeUploadResponse:
    """Finalize an existing file upload by file id.

    Canonical path: `/api/v1/files/{file_id}:finalize`.
    Legacy-compat alias: `/api/v1/files/{file_id}:complete`.
    """
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    resolved_file_id = payload.file_id or file_id
    file_record = await svc.finalize_upload(
        file_id=resolved_file_id,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
    )
    await BillingService(session).add_usage(
        tenant_id=str(tenant.id),
        s3_bytes_delta=int(file_record.size_bytes or 0),
        ref_id=file_record.id,
    )
    await session.commit()
    return FinalizeUploadResponse(file_id=file_record.id, status=file_record.status)


@router.get(
    "/records/{file_id}",
    response_model=FileDto,
    operation_id="files_get_record",
)
async def get_file_v2(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> FileDto:
    _enforce_access_role(access, _FILE_READ_ROLES)
    file_record = await session.get(FileRecord, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="file_not_found")
    enforce_row_belongs_to_tenant(
        session,
        file_record,
        tenant_id=str(tenant.id),
        mismatch_event="api.modules.files.get_record.tenant_scope_mismatch",
        detail="file_not_found",
    )
    await service.FileService(session=session, tenant_id=str(tenant.id)).ensure_record_access(
        record=file_record,
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
    )
    link_rows = (
        (
            await session.execute(
                select(FileLink).where(
                    FileLink.tenant_id == str(tenant.id),
                    FileLink.file_id == file_id,
                )
            )
        )
        .scalars()
        .all()
    )
    content_index = (
        await session.execute(select(FileContentIndex).where(FileContentIndex.file_id == file_id))
    ).scalar_one_or_none()
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
        links=[
            EntityFileListItem(
                file_id=file_record.id,
                role=link_row.role,
                status=file_record.status,
                display_name=Path(file_record.object_key).name,
                size=file_record.size_bytes,
            )
            for link_row in link_rows
        ],
        content_index=(
            FileIndexStatusDto(
                status=content_index.status,
                attempts=int(content_index.attempts or 0),
                last_error=content_index.last_error,
            )
            if content_index
            else None
        ),
    )


@router.post(
    "/{file_id}:reindex",
    response_model=ReindexFileResponse,
    operation_id="files_reindex",
)
async def reindex_file_content_v2(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReindexFileResponse:
    file_record = await session.get(FileRecord, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail="file_not_found")
    enforce_row_belongs_to_tenant(
        session,
        file_record,
        tenant_id=str(tenant.id),
        mismatch_event="api.modules.files.reindex.tenant_scope_mismatch",
        detail="file_not_found",
    )
    from app.tasks import index_file_content_job

    index_file_content_job.apply_async(
        kwargs={"tenant_slug": session.info.get("tenant"), "file_id": file_id},
        countdown=0,
    )
    return ReindexFileResponse(file_id=file_id, status="queued")


@router.get(
    "/{file_id}/download-url",
    response_model=DownloadUrlResponse,
    operation_id="files_get_download_url",
)
@router.post(
    "/{file_id}:download-url",
    response_model=DownloadUrlResponse,
    operation_id="files_post_download_url_legacy_compat",
)
async def get_download_url_v2(
    file_id: str,
    request: Request,
    payload: DownloadUrlRequest | None = None,
    purpose: str | None = None,
    ttl: int = 600,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> DownloadUrlResponse:
    """Resolve a signed download URL.

    Canonical path: `GET /api/v1/files/{file_id}/download-url`.
    Legacy-compat alias: `POST /api/v1/files/{file_id}:download-url`.
    """
    _enforce_access_role(access, _FILE_READ_ROLES)
    resolved_purpose = (payload.purpose if payload else purpose) or "download"
    resolved_ttl = payload.ttl_seconds if payload else ttl
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    url = await svc.get_signed_download_url(
        file_id=file_id,
        purpose=resolved_purpose,
        ttl=resolved_ttl,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        access=access,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return DownloadUrlResponse(signed_get_url=url)


@router.post("/{file_id}:link", response_model=LinkFileResponse, operation_id="files_link")
# legacy-compat alias for historical slash route shape.
@router.post(
    "/{file_id}/link",
    response_model=LinkFileResponse,
    operation_id="files_link_legacy_compat",
)
async def link_file_v2(
    file_id: str,
    payload: LinkFileRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> LinkFileResponse:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    role = payload.role or payload.tag or "attachment"
    link = await svc.link_file(
        file_id=file_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        role=role,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
        access=access,
    )
    await session.commit()
    return LinkFileResponse(link_id=link.id)


@router.get(
    "/entities/{entity_type}/{entity_id}/files",
    response_model=list[EntityFileListItem],
    operation_id="files_list_entity_files",
)
# legacy-compat alias used by older clients.
@router.get(
    "/entities/{entity_type}/{entity_id}/list",
    response_model=list[EntityFileListItem],
    operation_id="files_list_entity_files_legacy_compat",
)
async def list_entity_files_v2(
    entity_type: str,
    entity_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> list[EntityFileListItem]:
    _enforce_access_role(access, _FILE_READ_ROLES)
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
            link_id=link.id,
        )
        for link, file_rec in rows
    ]


@router.post(
    "/{file_id}:signed-url",
    response_model=SignedUrlResponse,
    operation_id="files_signed_url",
)
# legacy-compat alias for slash variant.
@router.post(
    "/{file_id}/signed-url",
    response_model=SignedUrlResponse,
    operation_id="files_signed_url_legacy_compat",
)
async def get_signed_url_v2(
    file_id: str,
    payload: SignedUrlRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> SignedUrlResponse:
    _enforce_access_role(access, _FILE_READ_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    url = await svc.get_signed_download_url(
        file_id=file_id,
        purpose=payload.action,
        ttl=payload.ttl_seconds,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        access=access,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return SignedUrlResponse(signed_url=url)


@router.delete(
    "/{file_id}/link/{link_id}",
    operation_id="files_delete_link",
)
async def delete_link_v2(
    file_id: str,
    link_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> dict[str, str]:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    await svc.unlink_file_by_id(file_id=file_id, link_id=link_id)
    await session.commit()
    return {"status": "deleted"}


@router.post("/abort-upload", operation_id="files_abort_upload")
async def abort_upload_v2(
    payload: CompleteUploadRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> dict[str, str]:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    await svc.abort_upload(file_id=payload.file_id)
    await session.commit()
    return {"status": "aborted"}


@router.post(
    "/upload-multipart",
    response_model=FinalizeUploadResponse,
    operation_id="files_upload_multipart",
)
async def upload_multipart_v1(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> FinalizeUploadResponse:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    reject_oversize_upload(
        file,
        code="FILE_UPLOAD_TOO_LARGE",
        error_type="files",
        message="Загружаемый файл превышает максимальный размер",
    )
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    filename = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"
    file_record, _upload_url, _ = await svc.create_upload_session(
        filename=filename,
        content_type=content_type,
        size_bytes=0,
        metadata_json={},
    )
    from app.modules.files import s3

    sha256 = hashlib.sha256()
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total_size += len(chunk)
        sha256.update(chunk)
        chunks.append(chunk)
    payload = b"".join(chunks)
    s3.put_object(data=payload, mime=content_type, key=file_record.object_key)
    file_record.size_bytes = total_size
    file_record.sha256 = sha256.hexdigest()
    file_record = await svc.finalize_upload(file_id=file_record.id)
    await session.commit()
    return FinalizeUploadResponse(file_id=file_record.id, status=file_record.status)


@router.get("", response_model=list[FileDto], operation_id="files_list")
async def list_files_v1(
    status: str | None = None,
    query: str | None = None,
    meta_document_version_id: str | None = Query(default=None, alias="meta.document_version_id"),
    updated_from: datetime | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> list[FileDto]:
    _enforce_access_role(access, _FILE_READ_ROLES)
    stmt = select(FileRecord).where(
        FileRecord.tenant_id == str(tenant.id),
        FileRecord.deleted_at.is_(None),
    )
    if status:
        stmt = stmt.where(FileRecord.status == status)
    if query:
        stmt = stmt.where(FileRecord.object_key.ilike(f"%{query}%"))
    if meta_document_version_id:
        stmt = stmt.where(
            FileRecord.metadata_json["document_version_id"].astext == meta_document_version_id
        )
    if updated_from:
        stmt = stmt.where(FileRecord.updated_at >= updated_from)
    rows = (
        (await session.execute(stmt.order_by(FileRecord.updated_at.desc()).limit(200)))
        .scalars()
        .all()
    )
    return [
        FileDto(
            id=r.id,
            bucket=r.bucket,
            object_key=r.object_key,
            content_type=r.content_type,
            size_bytes=r.size_bytes,
            sha256=r.sha256,
            status=r.status,
            av_vendor=r.av_vendor,
            av_result_json=r.av_result_json or {},
            metadata_json=r.metadata_json or {},
            links=[],
            content_index=None,
        )
        for r in rows
    ]


@router.post(
    "/{file_id}/new-version",
    response_model=NewFileVersionResponse,
    operation_id="files_create_new_version",
)
async def create_new_version_v1(
    file_id: str,
    payload: NewFileVersionRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> NewFileVersionResponse:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    await BillingService(session).assert_allowed(
        tenant,
        "files.upload",
        meta={"delta_bytes": int(payload.size_bytes)},
    )
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    version, upload_url, expires_in = await svc.create_new_version_upload_session(
        file_id=file_id,
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        metadata_json=payload.metadata
        or payload.metadata_json
        or ({"sha256": payload.sha256} if payload.sha256 else None),
    )
    await session.commit()
    return NewFileVersionResponse(
        file_id=file_id,
        version_id=version.id,
        signed_put_url=upload_url,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        status=version.status,
    )


@router.get(
    "/{file_id}/versions",
    response_model=list[FileVersionDto],
    operation_id="files_list_versions",
)
async def list_file_versions_v1(
    file_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = READ_ACCESS_DEP,
) -> list[FileVersionDto]:
    _enforce_access_role(access, _FILE_READ_ROLES)
    rows = (
        (
            await session.execute(
                select(FileVersion)
                .where(FileVersion.tenant_id == str(tenant.id), FileVersion.file_id == file_id)
                .order_by(FileVersion.version_no.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        FileVersionDto(
            id=v.id,
            file_id=v.file_id,
            sha256=v.sha256,
            size_bytes=v.size,
            s3_version_id=None,
            created_by=v.created_by,
            created_at=v.created_at,
        )
        for v in rows
    ]


@router.delete("/{file_id}", operation_id="files_delete")
async def delete_file_v1(
    file_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = WRITE_ACCESS_DEP,
) -> dict[str, str]:
    _enforce_access_role(access, _FILE_UPLOAD_ROLES)
    svc = service.FileService(session=session, tenant_id=str(tenant.id))
    await svc.delete_file(
        file_id=file_id,
        actor_id=getattr(access.user, "id", None),
        actor_role=getattr(access, "role", None),
        actor_company_id=access.company_id,
        access=access,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {"status": "deleted"}
