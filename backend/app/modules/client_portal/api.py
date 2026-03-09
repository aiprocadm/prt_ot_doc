from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.projections.models import ClientPortalReadModel, PortalRequest, PortalRequestMessage

router = APIRouter(prefix="/client-portal", tags=["client-portal-v1"])
internal_router = APIRouter(prefix="/portal-requests", tags=["portal-requests"])


class RequestCreate(BaseModel):
    title: str
    body: str
    package_id: str | None = None
    project_id: str | None = None
    client_company_id: str | None = None
    priority: str = "medium"


class RequestMessageCreate(BaseModel):
    body: str
    author_role: str = "client"


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    items = (await session.execute(select(ClientPortalReadModel).where(ClientPortalReadModel.tenant_id == str(tenant.id)).limit(20))).scalars().all()
    return {"items": items}


@router.get("/packages")
async def packages(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (
        await session.execute(
            select(ClientPortalReadModel).where(ClientPortalReadModel.tenant_id == str(tenant.id), ClientPortalReadModel.item_type == "package")
        )
    ).scalars().all()
    return rows


@router.get("/packages/{package_id}")
async def package_details(package_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    row = (
        await session.execute(
            select(ClientPortalReadModel).where(
                ClientPortalReadModel.tenant_id == str(tenant.id), ClientPortalReadModel.package_id == package_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Package not found")
    return row


@router.get("/requests")
async def list_requests(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    return (await session.execute(select(PortalRequest).where(PortalRequest.tenant_id == str(tenant.id), PortalRequest.deleted_at.is_(None)))).scalars().all()


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_request(payload: RequestCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    req = PortalRequest(tenant_id=str(tenant.id), title=payload.title, body=payload.body, package_id=payload.package_id, project_id=payload.project_id, client_company_id=payload.client_company_id, priority=payload.priority)
    session.add(req)
    await session.commit()
    await session.refresh(req)
    return req


@router.get("/requests/{request_id}")
async def get_request(request_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    req = (await session.execute(select(PortalRequest).where(PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    msgs = (await session.execute(select(PortalRequestMessage).where(PortalRequestMessage.portal_request_id == request_id, PortalRequestMessage.tenant_id == str(tenant.id)))).scalars().all()
    return {"request": req, "messages": msgs}


@router.post("/requests/{request_id}/messages", status_code=status.HTTP_201_CREATED)
async def create_request_message(request_id: str, payload: RequestMessageCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    req = (await session.execute(select(PortalRequest).where(PortalRequest.id == request_id, PortalRequest.tenant_id == str(tenant.id)))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    msg = PortalRequestMessage(tenant_id=str(tenant.id), portal_request_id=request_id, body=payload.body, author_role=payload.author_role)
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return msg


@internal_router.get("")
async def internal_requests(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    return (await session.execute(select(PortalRequest).where(PortalRequest.tenant_id == str(tenant.id), PortalRequest.deleted_at.is_(None)))).scalars().all()
