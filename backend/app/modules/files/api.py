from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.idempotency import compute_request_hash
from app.models.models import Tenant
from app.modules.files import service
from app.modules.files.schemas import DownloadURLResponse, UploadCompleteRequest, UploadInitRequest, UploadInitResponse
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


@router.post(":upload-complete")
async def upload_complete(payload: UploadCompleteRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict[str, str]:
    version = await service.complete_upload(session=session, tenant_id=str(tenant.id), file_id=payload.file_id, version_id=payload.version_id)
    await session.commit()
    return {"version_id": version.id, "status": version.status, "av_status": version.av_status}


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
