"""Unified Employee Card endpoint (vNext-EMP-01 / Phase 3.2).

Single read-only aggregate that powers the unified Employee Card UI.
Source of truth remains the underlying domain modules (persons, training,
medical, ppe, permits, incidents, audit); this route only joins them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.feature_flags import is_feature_enabled
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.privacy.service import PDN_FEATURE_CODE, PdnAccessJournal
from app.schemas.employee import EmployeeCard
from app.services.employee_card import EmployeeCardService

router = APIRouter(prefix="/employees", tags=["employees"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


# Roles that can read an employee card. Mirrors the access list used for HR /
# OT-PB workflows: admin/owner manage everyone; hr и line_manager — операционно;
# ot_pb_lead — для расследований/допусков. Расширяется при необходимости.
# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_EMPLOYEE_READ_ROLES = list(screen_roles("employee_card.view"))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


EmployeeReadAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_EMPLOYEE_READ_ROLES,
            action="read employee card",
        )
    ),
]


@router.get(
    "/{person_id}",
    response_model=EmployeeCard,
    summary="Unified Employee Card aggregate (Personal/Roles/Training/Medicals/PPE/Permits/Incidents/Audit)",
)
async def get_employee_card(
    person_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EmployeeReadAccess,
) -> EmployeeCard:
    TenantContextValidator.ensure_tenant_context(tenant)

    service = EmployeeCardService(tenant_id=str(tenant.id), db=session)
    card = await service.build(person_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")

    # SEC-66 разд. 66.2: карточка — основная поверхность чтения ПДн, поэтому
    # обращение попадает в журнал доступа субъекта. 404 не журналируем: субъекта нет.
    if await is_feature_enabled(session, str(tenant.id), PDN_FEATURE_CODE, default=True):
        role = getattr(access.user, "role", None)
        await PdnAccessJournal(session).record(
            tenant_id=str(tenant.id),
            subject_person_id=person_id,
            action="view_card",
            actor_user_id=str(access.user.id) if access.user else None,
            actor_email=getattr(access.user, "email", None),
            actor_role=getattr(role, "value", None) or (str(role) if role else None),
            ip=request.client.host if request.client else "unknown",
            request_id=request.headers.get("x-request-id"),
        )
        await session.commit()
    return card
