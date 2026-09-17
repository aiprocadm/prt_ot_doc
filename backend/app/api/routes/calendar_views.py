"""Saved Smart Calendar views endpoints (vNext-CAL-01 / Phase 4.1).

Per-user CRUD on filter presets stored as JSON. RBAC mirrors
`calendar.py`: any role that can read the calendar can manage their own
saved views (admin/owner + HSE roles). Each user only sees their own
views — tenant scoping plus `user_id` scoping are both enforced by the
service layer.

Routes (all under `/api/v1/calendar/saved-views`):
* `GET /`              — list current user's saved views (oldest first).
* `POST /`             — create a new saved view.
* `PATCH /{view_id}`   — full replace of `name` + `payload`.
* `DELETE /{view_id}`  — remove a saved view.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.models.calendar_views import SavedCalendarView
from app.models.models import Tenant
from app.schemas.calendar_views import (
    SavedCalendarView as SavedCalendarViewDto,
)
from app.schemas.calendar_views import (
    SavedCalendarViewCreateRequest,
    SavedCalendarViewPayload,
    SavedCalendarViewUpdateRequest,
)
from app.services.calendar_views import (
    CalendarViewsService,
    SavedCalendarViewNameConflictError,
)

router = APIRouter(
    prefix="/calendar/saved-views",
    tags=["calendar", "calendar-saved-views"],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_CALENDAR_VIEW_ROLES = list(screen_roles("calendar.view"))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


CalendarViewAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_CALENDAR_VIEW_ROLES,
            action="manage calendar saved views",
        )
    ),
]


def _to_dto(view: SavedCalendarView) -> SavedCalendarViewDto:
    return SavedCalendarViewDto(
        id=str(view.id),
        name=view.name,
        payload=SavedCalendarViewPayload(**(view.payload or {})),
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


def _service_for(
    *, session: AsyncSession, tenant: Tenant, access: AccessContext
) -> CalendarViewsService:
    user_id = getattr(access.user, "id", None) if access else None
    if user_id is None:
        # An authenticated user is required to scope rows.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authenticated user required",
        )
    return CalendarViewsService(
        db=session,
        tenant_id=str(tenant.id),
        user_id=str(user_id),
    )


@router.get(
    "",
    response_model=list[SavedCalendarViewDto],
    summary="List current user's saved Smart Calendar views",
)
async def list_saved_views(
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarViewAccess,
) -> list[SavedCalendarViewDto]:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = _service_for(session=session, tenant=tenant, access=access)
    rows = await service.list_views()
    return [_to_dto(row) for row in rows]


@router.post(
    "",
    response_model=SavedCalendarViewDto,
    status_code=status.HTTP_201_CREATED,
    summary="Create a saved Smart Calendar view for the current user",
)
async def create_saved_view(
    payload: SavedCalendarViewCreateRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarViewAccess,
) -> SavedCalendarViewDto:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = _service_for(session=session, tenant=tenant, access=access)
    try:
        created = await service.create(
            name=payload.name,
            payload=payload.payload.model_dump(mode="json"),
        )
    except SavedCalendarViewNameConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(created)
    return _to_dto(created)


@router.patch(
    "/{view_id}",
    response_model=SavedCalendarViewDto,
    summary="Update name and payload of a saved Smart Calendar view",
)
async def update_saved_view(
    view_id: str,
    payload: SavedCalendarViewUpdateRequest,
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarViewAccess,
) -> SavedCalendarViewDto:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = _service_for(session=session, tenant=tenant, access=access)
    view = await service.get(view_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved view not found")
    try:
        updated = await service.update(
            view,
            name=payload.name,
            payload=payload.payload.model_dump(mode="json"),
        )
    except SavedCalendarViewNameConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before refresh (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(updated)
    return _to_dto(updated)


@router.delete(
    "/{view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete a saved Smart Calendar view",
)
async def delete_saved_view(
    view_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: CalendarViewAccess,
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = _service_for(session=session, tenant=tenant, access=access)
    view = await service.get(view_id)
    if view is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved view not found")
    await service.delete(view)
    await session.commit()
