from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import String, asc, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import api_key_auth
from app.models.document import Document
from app.models.models import (
    ApiKey,
    ClientPackagePreset,
    Incident,
    Inspection,
    MarketplaceCatalogItem,
    Person,
    Prescription,
    Tenant,
    TrainingEnrollment,
    WebhookEndpoint,
)
from app.models.notifications import Notification
from app.models.risk import RiskAssessment
from app.modules.projections.models import ExportJob
from app.services.api_keys import create_api_key, rotate_api_key

router = APIRouter(prefix="/public", tags=["public-api"])
admin_router = APIRouter(prefix="/machine-keys", tags=["machine-keys"])
marketplace_router = APIRouter(prefix="/marketplace", tags=["marketplace"])


class MachineKeyCreate(BaseModel):
    name: str
    scopes: list[str] = Field(default_factory=list)
    rate_limit_per_minute: int | None = None


class PublicListEnvelope(BaseModel):
    items: list[dict] | list
    total: int
    limit: int
    offset: int
    sort_by: str
    sort_order: str


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


class MarketplaceInstallRequest(BaseModel):
    mode: str = "install"
    target_code: str | None = None
    title_suffix: str | None = None


class PublicWebhookSubscriptionCreate(BaseModel):
    name: str
    url: str
    subscribed_events: list[str] = Field(default_factory=list)
    timeout_ms: int = 5000
    headers: dict[str, Any] = Field(default_factory=dict)


def _ensure_scope(record: ApiKey, scope: str) -> None:
    if scope not in record.scope_list and "api:admin" not in record.scope_list:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            {"code": "scope_denied", "message": f"Missing scope: {scope}"},
        )


@admin_router.get("")
async def list_machine_keys(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
):
    rows = (
        (
            await session.execute(
                select(ApiKey)
                .where(ApiKey.tenant_id == tenant.id)
                .order_by(ApiKey.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "scopes": row.scope_list,
                "is_active": row.is_active,
                "usage_count": row.usage_count,
                "last_used_at": row.last_used_at,
                "revoked_at": row.revoked_at,
                "last_rotated_at": row.last_rotated_at,
                "rate_limit_per_minute": row.rate_limit_per_minute,
                "key_prefix": row.key_prefix,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@admin_router.post("", status_code=status.HTTP_201_CREATED)
@audit_operation("issue", "machine_key")
async def issue_machine_key(
    payload: MachineKeyCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    secret = await create_api_key(
        session, tenant_id=str(tenant.id), name=payload.name, scopes=payload.scopes or ["api:read"]
    )
    secret.record.rate_limit_per_minute = payload.rate_limit_per_minute
    await session.commit()
    await session.refresh(secret.record)
    return {
        "id": secret.record.id,
        "name": secret.record.name,
        "scopes": secret.record.scope_list,
        "token": secret.value,
        "rate_limit_per_minute": secret.record.rate_limit_per_minute,
    }


@admin_router.post("/{item_id}/revoke")
@audit_operation("revoke", "machine_key")
async def revoke_machine_key(
    item_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    record = await session.get(ApiKey, item_id)
    if not record or record.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine key not found")
    record.is_active = False
    record.revoked_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return {"status": "revoked"}


@admin_router.post("/{item_id}/rotate")
@audit_operation("rotate", "machine_key")
async def rotate_machine_key(
    item_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    record = await session.get(ApiKey, item_id)
    if not record or record.tenant_id != tenant.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Machine key not found")
    rotated = await rotate_api_key(session, record=record)
    rotated.record.rate_limit_per_minute = record.rate_limit_per_minute
    rotated.record.last_rotated_at = datetime.now(tz=timezone.utc)
    await session.commit()
    await session.refresh(rotated.record)
    return {
        "id": rotated.record.id,
        "name": rotated.record.name,
        "scopes": rotated.record.scope_list,
        "token": rotated.value,
        "rate_limit_per_minute": rotated.record.rate_limit_per_minute,
        "rotated_from_id": item_id,
    }


@router.get("/auth/machine")
async def machine_auth_info(record: ApiKey = Depends(api_key_auth)):
    return {
        "subject": f"api_key:{record.id}",
        "tenant_id": str(record.tenant_id),
        "scopes": record.scope_list,
        "usage_count": record.usage_count,
    }


def _apply_filters(stmt, model, q: str | None, status_value: str | None):
    if status_value and hasattr(model, "status"):
        stmt = stmt.where(getattr(model, "status") == status_value)
    if q:
        text_columns = [name for name in ("name", "title", "code") if hasattr(model, name)]
        if text_columns:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(*[cast(getattr(model, col), String).ilike(pattern) for col in text_columns])
            )
    return stmt


async def _tenant_scoped_list(
    model,
    tenant_id: str,
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
    q: str | None = None,
    status_value: str | None = None,
):
    limit = max(1, min(limit, 100))
    offset = max(offset, 0)
    sort_column = getattr(model, sort_by, None) or getattr(model, "updated_at")
    order_by = desc(sort_column) if sort_order.lower() == "desc" else asc(sort_column)
    base_stmt = _apply_filters(
        select(model).where(model.tenant_id == tenant_id), model, q, status_value
    )
    total = int(
        (await session.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one()
    )
    rows = (
        (await session.execute(base_stmt.order_by(order_by).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    return {
        "items": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort_by": getattr(sort_column, "key", sort_by),
        "sort_order": sort_order.lower(),
    }


@router.get("/employees")
async def public_employees(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    q: str | None = Query(default=None),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "employees:read")
    return await _tenant_scoped_list(
        Person,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        q=q,
    )


@router.get("/documents")
async def public_documents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "documents:read")
    return await _tenant_scoped_list(
        Document,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        q=q,
        status_value=status_value,
    )


@router.get("/training")
async def public_training(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "training:read")
    return await _tenant_scoped_list(
        TrainingEnrollment,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/risks")
async def public_risks(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "risks:read")
    return await _tenant_scoped_list(
        RiskAssessment,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/incidents")
async def public_incidents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "incidents:read")
    return await _tenant_scoped_list(
        Incident,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/inspections")
async def public_inspections(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "inspections:read")
    return await _tenant_scoped_list(
        Inspection,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/prescriptions")
async def public_prescriptions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "prescriptions:read")
    return await _tenant_scoped_list(
        Prescription,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/notifications")
async def public_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "notifications:read")
    return await _tenant_scoped_list(
        Notification,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/reports/exports")
async def public_exports(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    status_value: str | None = Query(default=None, alias="status"),
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "exports:read")
    return await _tenant_scoped_list(
        ExportJob,
        str(record.tenant_id),
        session,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
        status_value=status_value,
    )


@router.get("/integrations/webhooks")
async def public_webhooks(
    record: ApiKey = Depends(api_key_auth), session: AsyncSession = Depends(get_session)
):
    _ensure_scope(record, "integrations:read")
    rows = (
        (
            await session.execute(
                select(WebhookEndpoint)
                .where(WebhookEndpoint.tenant_id == str(record.tenant_id))
                .order_by(WebhookEndpoint.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "url": row.url,
                "enabled": row.is_enabled,
                "subscribed_events": row.subscribed_events or [],
                "timeout_ms": row.timeout_ms,
                "updated_at": row.updated_at,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/integrations/webhooks/subscriptions", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "webhook_subscription")
async def create_public_webhook_subscription(
    payload: PublicWebhookSubscriptionCreate,
    record: ApiKey = Depends(api_key_auth),
    session: AsyncSession = Depends(get_session),
):
    _ensure_scope(record, "integrations:write")
    row = WebhookEndpoint(
        tenant_id=str(record.tenant_id),
        name=payload.name,
        url=payload.url,
        is_enabled=True,
        subscribed_events=payload.subscribed_events,
        timeout_ms=payload.timeout_ms,
        headers=payload.headers,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return {
        "id": row.id,
        "name": row.name,
        "url": row.url,
        "enabled": row.is_enabled,
        "subscribed_events": row.subscribed_events or [],
        "timeout_ms": row.timeout_ms,
        "updated_at": row.updated_at,
    }


@marketplace_router.get("")
async def list_marketplace(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    item_type: str | None = None,
    status_value: str | None = None,
):
    stmt = select(MarketplaceCatalogItem).where(
        MarketplaceCatalogItem.tenant_id == tenant.id, MarketplaceCatalogItem.deleted_at.is_(None)
    )
    if item_type:
        stmt = stmt.where(MarketplaceCatalogItem.item_type == item_type)
    if status_value:
        stmt = stmt.where(MarketplaceCatalogItem.status == status_value)
    rows = (
        (await session.execute(stmt.order_by(MarketplaceCatalogItem.updated_at.desc())))
        .scalars()
        .all()
    )
    return {"items": rows, "total": len(rows)}


@marketplace_router.post("", status_code=status.HTTP_201_CREATED)
@audit_operation("publish", "marketplace_item")
async def publish_marketplace_item(
    payload: MarketplaceItemCreate,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    item = MarketplaceCatalogItem(tenant_id=tenant.id, status="published", **payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@marketplace_router.post("/{item_id}/install")
@audit_operation("install", "marketplace_item")
async def install_marketplace_item(
    item_id: str,
    payload: MarketplaceInstallRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
):
    item = await session.get(MarketplaceCatalogItem, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Marketplace item not found")
    item.usage_count += 1
    installed_ref: dict[str, str] | None = None
    if item.item_type == "package_preset":
        source_payload = (
            item.preview_json.get("package_preset") if isinstance(item.preview_json, dict) else None
        )
        if isinstance(source_payload, dict):
            preset = ClientPackagePreset(
                tenant_id=tenant.id,
                code=payload.target_code or source_payload.get("code") or f"{item.code}-installed",
                name=f"{source_payload.get('name') or item.name}{payload.title_suffix or ''}",
                description=source_payload.get("description") or item.description,
                steps_json=source_payload.get("steps_json") or {},
                required_inputs_json=source_payload.get("required_inputs_json") or [],
                is_active=True,
            )
            session.add(preset)
            await session.flush()
            installed_ref = {"entity_type": "package_preset", "entity_id": preset.id}
    await session.commit()
    return {
        "status": payload.mode,
        "item_id": item.id,
        "usage_count": item.usage_count,
        "installed_ref": installed_ref,
    }
