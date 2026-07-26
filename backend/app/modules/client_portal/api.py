from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.upload import reject_oversize_upload
from app.core.security import AccessContext, abac
from app.db.session import rearm_session_tenant_context
from app.models.models import Tenant
from app.modules.client_portal.services import ClientPortalService
from app.modules.projections.models import (
    ClientPortalReadModel,
    PortalRequest,
    PortalRequestMessage,
)

router = APIRouter(prefix="/client-portal", tags=["client-portal-v1"])
internal_router = APIRouter(prefix="/portal-requests", tags=["portal-requests"])
logger = logging.getLogger(__name__)


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


PortalAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=["admin", "employee", "client_admin", "client_user"],
            action="access client portal",
        )
    ),
]

PortalInternalAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=["admin", "employee"],
            action="manage client portal requests",
        )
    ),
]


class RequestCreate(BaseModel):
    title: str
    body: str
    package_id: str | None = None
    project_id: str | None = None
    client_company_id: str | None = None
    priority: str = "medium"


class RequestPatch(BaseModel):
    status: str | None = None
    priority: str | None = None


class RequestMessageCreate(BaseModel):
    body: str
    author_role: str = "client"


async def _safe_list_items(
    service: ClientPortalService,
    *,
    client_company_id: str | None = None,
    item_type: str | None = None,
) -> list[dict]:
    try:
        return await service.list_items(client_company_id=client_company_id, item_type=item_type)
    except (OperationalError, ProgrammingError):
        # Dockerless SQLite may miss projection tables; keep dashboard stable instead of 500.
        logger.warning(
            "client_portal.read_model_unavailable",
            extra={"client_company_id": client_company_id, "item_type": item_type},
            exc_info=True,
        )
        return []


@router.get("/dashboard")
async def dashboard(
    client_company_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    items = await _safe_list_items(
        ClientPortalService(session, str(tenant.id)),
        client_company_id=client_company_id,
    )
    return {"items": items[:20]}


@router.get("/packages")
async def packages(
    client_company_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    return await _safe_list_items(
        ClientPortalService(session, str(tenant.id)),
        client_company_id=client_company_id,
        item_type="package",
    )


@router.get("/packages/{package_id}")
async def package_details(
    package_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    row = (
        await session.execute(
            select(ClientPortalReadModel).where(
                ClientPortalReadModel.tenant_id == str(tenant.id),
                ClientPortalReadModel.package_id == package_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return row


@router.get("/documents")
async def documents(
    client_company_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    return await _safe_list_items(
        ClientPortalService(session, str(tenant.id)),
        client_company_id=client_company_id,
        item_type="document_bundle",
    )


@router.get("/history")
async def history(
    client_company_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    return await _safe_list_items(
        ClientPortalService(session, str(tenant.id)),
        client_company_id=client_company_id,
    )


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def uploads(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    reject_oversize_upload(
        file,
        code="PORTAL_UPLOAD_TOO_LARGE",
        error_type="client_portal",
        message="Загружаемый файл превышает максимальный размер",
    )
    return {"tenant_id": str(tenant.id), "filename": file.filename, "size": len(await file.read())}


@router.get("/requests")
async def list_requests(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    return (
        (
            await session.execute(
                select(PortalRequest).where(
                    PortalRequest.tenant_id == str(tenant.id), PortalRequest.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(
    payload: RequestCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    req = PortalRequest(
        tenant_id=str(tenant.id),
        title=payload.title,
        body=payload.body,
        package_id=payload.package_id,
        project_id=payload.project_id,
        client_company_id=payload.client_company_id,
        priority=payload.priority,
    )
    session.add(req)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(req)
    return req


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    req = (
        await session.execute(
            select(PortalRequest).where(
                PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    msgs = (
        (
            await session.execute(
                select(PortalRequestMessage).where(
                    PortalRequestMessage.portal_request_id == request_id,
                    PortalRequestMessage.tenant_id == str(tenant.id),
                )
            )
        )
        .scalars()
        .all()
    )
    return {"request": req, "messages": msgs}


@router.post("/requests/{request_id}/messages", status_code=status.HTTP_201_CREATED)
async def create_request_message(
    request_id: str,
    payload: RequestMessageCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalAccess,
):
    req = (
        await session.execute(
            select(PortalRequest).where(
                PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    msg = PortalRequestMessage(
        tenant_id=str(tenant.id),
        portal_request_id=request_id,
        body=payload.body,
        author_role=payload.author_role,
    )
    session.add(msg)
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(msg)
    return msg


@internal_router.get("")
async def internal_requests(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalInternalAccess,
):
    return (
        (
            await session.execute(
                select(PortalRequest).where(
                    PortalRequest.tenant_id == str(tenant.id), PortalRequest.deleted_at.is_(None)
                )
            )
        )
        .scalars()
        .all()
    )


@internal_router.get("/{request_id}")
async def internal_request_by_id(
    request_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalInternalAccess,
):
    req = (
        await session.execute(
            select(PortalRequest).where(
                PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


@internal_router.patch("/{request_id}")
async def internal_request_patch(
    request_id: str,
    payload: RequestPatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalInternalAccess,
):
    req = (
        await session.execute(
            select(PortalRequest).where(
                PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)
            )
        )
    ).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if payload.status:
        req.status = payload.status
    if payload.priority:
        req.priority = payload.priority
    req.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return req


@internal_router.post("/{request_id}/messages", status_code=status.HTTP_201_CREATED)
async def internal_request_message(
    request_id: str,
    payload: RequestMessageCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    *,
    access: PortalInternalAccess,
):
    return await create_request_message(
        request_id=request_id,
        payload=payload,
        session=session,
        tenant=tenant,
        access=access,
    )
