"""Unified Employee Card endpoint (vNext-EMP-01 / Phase 3.2).

Single read-only aggregate that powers the unified Employee Card UI.
Source of truth remains the underlying domain modules (persons, training,
medical, ppe, permits, incidents, audit); this route only joins them.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.schemas.employee import EmployeeCard
from app.services.employee_card import EmployeeCardService

router = APIRouter(prefix="/employees", tags=["employees"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


# Roles that can read an employee card. Mirrors the access list used for HR /
# OT-PB workflows: admin/owner manage everyone; hr и line_manager — операционно;
# ot_pb_lead — для расследований/допусков. Расширяется при необходимости.
_EMPLOYEE_READ_ROLES = ["admin", "owner", "hr", "line_manager", "ot_pb_lead"]


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
    tenant: TenantDep,
    session: SessionDep,
    access: EmployeeReadAccess,
) -> EmployeeCard:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access

    service = EmployeeCardService(tenant_id=str(tenant.id), db=session)
    card = await service.build(person_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return card
