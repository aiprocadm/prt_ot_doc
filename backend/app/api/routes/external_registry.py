from __future__ import annotations

from typing import Annotated

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, rbac
from app.models.models import ExternalRegistryJob, Tenant
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/external-registry", tags=["external-registry"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_EXTERNAL_REGISTRY_READ_ROLES = ["admin", "owner", "integrations"]
_EXTERNAL_REGISTRY_WRITE_ROLES = ["admin", "owner", "integrations"]

ReaderAccess = Annotated[
    AccessContext,
    Depends(rbac(_EXTERNAL_REGISTRY_READ_ROLES)),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(rbac(_EXTERNAL_REGISTRY_WRITE_ROLES)),
]


@router.get("/jobs")
async def list_jobs(
    tenant: TenantDep,
    session: SessionDep,
    _: ReaderAccess,
):
    items = (await session.execute(select(ExternalRegistryJob).where(ExternalRegistryJob.tenant_id == tenant.id).order_by(ExternalRegistryJob.created_at.desc()))).scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/webhooks/frdo")
@audit_operation("webhook", "external_registry_frdo")
async def frdo_webhook(
    payload: dict,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
):
    return {"ok": True, "provider": "frdo", "payload": payload}


@router.post("/webhooks/eisot")
@audit_operation("webhook", "external_registry_eisot")
async def eisot_webhook(
    payload: dict,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
):
    return {"ok": True, "provider": "eisot", "payload": payload}
