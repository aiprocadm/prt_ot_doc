from __future__ import annotations

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.models.models import ExternalRegistryJob, Tenant
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/external-registry", tags=["external-registry"])


@router.get("/jobs")
async def list_jobs(tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(ExternalRegistryJob).where(ExternalRegistryJob.tenant_id == tenant.id).order_by(ExternalRegistryJob.created_at.desc()))).scalars().all()
    return {"items": items, "total": len(items)}


@router.post("/webhooks/frdo")
@audit_operation("webhook", "external_registry_frdo")
async def frdo_webhook(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    return {"ok": True, "provider": "frdo", "payload": payload}


@router.post("/webhooks/eisot")
@audit_operation("webhook", "external_registry_eisot")
async def eisot_webhook(payload: dict, tenant: Tenant = Depends(get_tenant_record), session: AsyncSession = Depends(get_session)):
    return {"ok": True, "provider": "eisot", "payload": payload}
