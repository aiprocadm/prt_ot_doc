from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.files import service
from app.modules.files.schemas import DownloadURLResponse, UploadCompleteRequest, UploadInitRequest, UploadInitResponse

router = APIRouter()


@router.post(":upload-init", response_model=UploadInitResponse)
async def upload_init(payload: UploadInitRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> UploadInitResponse:
    obj, version, url = await service.create_upload_session(session=session, tenant_id=str(tenant.id), payload=payload, user_id=None)
    await session.commit()
    return UploadInitResponse(file_id=obj.id, version_id=version.id, upload_url=url, s3_key=version.s3_key)


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
