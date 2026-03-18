from __future__ import annotations

from datetime import datetime, timezone

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import api_key_auth
from app.models.document import Document
from app.models.models import (
    ApiKey,
    Incident,
    Inspection,
    MarketplaceCatalogItem,
    Person,
    Prescription,
    Tenant,
    TrainingEnrollment,
)
from app.models.notifications import Notification
from app.models.risk import RiskAssessment
from app.modules.projections.models import ExportJob
from app.services.api_keys import create_api_key
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/public", tags=["public-api"])
admin_router = APIRouter(prefix="/machine-keys", tags=["machine-keys"])
marketplace_router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class MachineKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int | None = None


class MarketplaceItemCreate(BaseModel):
    item_type: str
    code: str
    name: str
    version_label: str
    category: str | None = None
    tags_json: list[str] = Field(default_factory=list)
    description: str | None = None
    preview_json: dict = Field(default_factory=dict)
    compatibility_json: dict = Field(default_factory=dict)
    dependency_json: dict = Field(default_factory=dict)
    source_ref: str | None = None


def _ensure_scope(record: ApiKey, scope: str) -> None:
    if scope not in record.scope_list and "api:admin" not in record.scope_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, {"code": "scope_denied", "message": f"Missing scope: {scope}"})


@admin_router.get("")
async def list_machine_keys(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    rows = (await session.execute(select(ApiKey).where(ApiKey.tenant_id == tenant.id).order_by(ApiKey.created_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@admin_router.post("", status_code=status.HTTP_201_CREATED)
async def issue_machine_key(payload: MachineKeyCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    secret = await create_api_key(session, tenant_id=str(tenant.id), name=payload.name, scopes=payload.scopes or ["api:read"])
    secret.record.rate_limit_per_minute = payload.rate_limit_per_minute
    await session.commit()
    await session.refresh(secret.record)
    return {"id": secret.record.id, "name": secret.record.name, "scopes": secret.record.scope_list, "token": secret.value, "rate_limit_per_minute": secret.record.rate_limit_per_minute}


@admin_router.post("/{item_id}/revoke")
async def revoke_machine_key(item_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    record = await session.get(ApiKey, item_id)
    if not record or record.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine key not found")
    record.is_active = False
    record.revoked_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "revoked"}


@router.get("/auth/machine")
async def machine_auth_info(record: ApiKey = Depends(api_key_auth)):
    return {"subject": f"api_key:{record.id}", "tenant_id": str(record.tenant_id), "scopes": record.scope_list, "usage_count": record.usage_count}


async def _tenant_scoped_list(model, tenant_id: str, session: AsyncSession):
    rows = (await session.execute(select(model).where(model.tenant_id == tenant_id).limit(100))).scalars().all()
    return {"items": rows, "total": len(rows)}


@router.get("/employees")
async def public_employees(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "employees:read")
    return await _tenant_scoped_list(Person, str(record.tenant_id), session)


@router.get("/documents")
async def public_documents(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "documents:read")
    return await _tenant_scoped_list(Document, str(record.tenant_id), session)


@router.get("/training")
async def public_training(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "training:read")
    return await _tenant_scoped_list(TrainingEnrollment, str(record.tenant_id), session)


@router.get("/risks")
async def public_risks(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "risks:read")
    return await _tenant_scoped_list(RiskAssessment, str(record.tenant_id), session)


@router.get("/incidents")
async def public_incidents(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "incidents:read")
    return await _tenant_scoped_list(Incident, str(record.tenant_id), session)


@router.get("/inspections")
async def public_inspections(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "inspections:read")
    return await _tenant_scoped_list(Inspection, str(record.tenant_id), session)


@router.get("/prescriptions")
async def public_prescriptions(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "prescriptions:read")
    return await _tenant_scoped_list(Prescription, str(record.tenant_id), session)


@router.get("/notifications")
async def public_notifications(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "notifications:read")
    return await _tenant_scoped_list(Notification, str(record.tenant_id), session)


@router.get("/reports/exports")
async def public_exports(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "exports:read")
    return await _tenant_scoped_list(ExportJob, str(record.tenant_id), session)


@router.get("/integrations/webhooks")
async def public_webhooks(record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)):
    _ensure_scope(record, "integrations:read")
    return {"items": [], "total": 0, "status": "foundation"}


@marketplace_router.get("")
async def list_marketplace(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record), item_type: str | None = None, status_value: str | None = None):
    stmt = select(MarketplaceCatalogItem).where(MarketplaceCatalogItem.tenant_id == tenant.id, MarketplaceCatalogItem.deleted_at.is_(None))
    if item_type:
        stmt = stmt.where(MarketplaceCatalogItem.item_type == item_type)
    if status_value:
        stmt = stmt.where(MarketplaceCatalogItem.status == status_value)
    rows = (await session.execute(stmt.order_by(MarketplaceCatalogItem.updated_at.desc()))).scalars().all()
    return {"items": rows, "total": len(rows)}


@marketplace_router.post("", status_code=status.HTTP_201_CREATED)
async def publish_marketplace_item(payload: MarketplaceItemCreate, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    item = MarketplaceCatalogItem(tenant_id=tenant.id, status="published", **payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@marketplace_router.post("/{item_id}/install")
async def install_marketplace_item(item_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)):
    item = await session.get(MarketplaceCatalogItem, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Marketplace item not found")
    item.usage_count += 1
    await session.commit()
    return {"status": "installed", "item_id": item.id, "usage_count": item.usage_count}
