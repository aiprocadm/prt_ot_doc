from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.notifications import (
    CalendarEventRead,
    ChannelSettingsIn,
    ChannelSettingsOut,
    MarkReadRequest,
    NotificationApplicationService,
    NotificationPage,
    NotificationTemplateIn,
    NotificationTemplateOut,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AccessDep = Annotated[AccessContext, Depends(rbac())]

# The per-user inbox / settings endpoints stay authn-only (`AccessDep`) — they are
# scoped by `access.user.id`. Notification *templates* are tenant-wide config, so
# they get least-privilege role gating mirroring 618614d9: read = MGMT_READ,
# write = DOC_WRITE.
_TEMPLATE_READ_ROLES = [
    "admin",
    "owner",
    "hr",
    "line_manager",
    "manager",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "accountant",
    "auditor_ro",
]
_TEMPLATE_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


TemplateReadAccess = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_TEMPLATE_READ_ROLES,
        action="read notification templates",
    )
)
TemplateWriteAccess = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_TEMPLATE_WRITE_ROLES,
        action="manage notification templates",
    )
)


def _service(
    session: AsyncSession, tenant: Tenant, access: AccessContext
) -> NotificationApplicationService:
    return NotificationApplicationService(session=session, tenant=tenant, user_id=access.user.id)


@router.get("", response_model=NotificationPage)
async def list_notifications(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> NotificationPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await _service(session, tenant, access).list_notifications(
        status_value=status,
        priority_value=priority,
        channel_value=channel,
        type_value=type,
        limit=limit,
        cursor=cursor,
    )


@router.post("/mark-read")
@audit_operation("mark_read", "notification")
async def mark_read(
    payload: MarkReadRequest,
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)

    updated = await _service(session, tenant, access).mark_read(payload.ids)
    return {"updated": updated}


@router.get("/notification-settings/me", response_model=ChannelSettingsOut)
async def get_settings_alias(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> ChannelSettingsOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await get_settings(session=session, tenant=tenant, access=access)


@router.put("/notification-settings/me", response_model=ChannelSettingsOut)
async def put_settings_alias(
    payload: ChannelSettingsIn,
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> ChannelSettingsOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await put_settings(payload=payload, session=session, tenant=tenant, access=access)


@router.get("/templates", response_model=list[NotificationTemplateOut])
async def list_templates(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessContext = TemplateReadAccess,
    channel: str | None = Query(default=None),
    type: str | None = Query(default=None),
) -> list[NotificationTemplateOut]:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await _service(session, tenant, access).list_templates(
        channel_value=channel,
        type_value=type,
    )


@router.post("/templates", response_model=NotificationTemplateOut)
@audit_operation("upsert", "notification_template")
async def upsert_template(
    payload: NotificationTemplateIn,
    session: SessionDep,
    tenant: TenantDep,
    access: AccessContext = TemplateWriteAccess,
) -> NotificationTemplateOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await _service(session, tenant, access).upsert_template(payload)


@router.get("/calendar/events", response_model=list[CalendarEventRead])
async def list_calendar_events(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> list[CalendarEventRead]:
    return await _service(session, tenant, access).list_calendar_events(
        status_value=status,
        source=source,
    )


@router.get("/settings/me", response_model=ChannelSettingsOut)
async def get_settings(
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> ChannelSettingsOut:
    TenantContextValidator.ensure_tenant_context(tenant)

    return await _service(session, tenant, access).get_settings()


@router.put("/settings/me", response_model=ChannelSettingsOut)
@audit_operation("update", "notification_settings")
async def put_settings(
    payload: ChannelSettingsIn,
    session: SessionDep,
    tenant: TenantDep,
    access: AccessDep,
) -> ChannelSettingsOut:
    return await _service(session, tenant, access).update_settings(payload)
