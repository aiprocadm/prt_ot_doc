"""Medical requirement endpoints — shared foundation (ARCH-4 slice 7 split).

The single ``router``, access dependencies, role constants, the medical feature gate
and the shared error/getter helpers used by the exams, catalog and contingent modules.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.domains.medical import lifecycle as lc
from app.models.models import (
    MedicalFactor,
    MedicalNorm,
    MedicalReferral,
    PsychiatricActivityType,
    Tenant,
)
from app.models.risk import RiskHazard
from app.schemas.medical import (
    MedicalReferralRead,
)

router = APIRouter(tags=["medical"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_MEDICAL_WRITE_ROLES = ["admin", "owner", "hr"]
_MEDICAL_READ_ROLES = ["admin", "owner", "hr", "line_manager"]


MedicalAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_MEDICAL_WRITE_ROLES, action="manage medical")
    ),
]
MedicalReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MEDICAL_READ_ROLES, action="read medical")),
]

_MEDICAL_FEATURE_CODE = "medical"


async def require_medical_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _MEDICAL_FEATURE_CODE):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Medical feature is not enabled for this tenant"
        )


MedicalFeatureGate = Depends(require_medical_feature)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _to_referral_read(record: MedicalReferral, *, today) -> MedicalReferralRead:
    return MedicalReferralRead.model_validate(record).model_copy(
        update={"is_overdue": lc.is_overdue(record.due_at, record.status, today)}
    )


async def _get_factor(session: AsyncSession, tenant_id: str, factor_id: str) -> MedicalFactor:
    rec = (
        await session.execute(
            select(MedicalFactor).where(
                MedicalFactor.id == factor_id,
                MedicalFactor.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_factor_not_found", "Medical factor not found"),
        )
    return rec


async def _get_hazard(session: AsyncSession, tenant_id: str, hazard_id: str) -> RiskHazard:
    rec = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.id == hazard_id,
                RiskHazard.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("hazard_not_found", "Hazard not found"),
        )
    return rec


async def _get_norm(session: AsyncSession, tenant_id: str, norm_id: str) -> MedicalNorm:
    from app.models.models import MedicalNorm as _MN

    rec = (
        await session.execute(
            select(_MN).where(
                _MN.id == norm_id,
                _MN.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_norm_not_found", "Medical norm not found"),
        )
    return rec


async def _get_referral(session: AsyncSession, tenant_id: str, referral_id: str) -> MedicalReferral:
    rec = (
        await session.execute(
            select(MedicalReferral).where(
                MedicalReferral.id == referral_id,
                MedicalReferral.tenant_id == tenant_id,
                MedicalReferral.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("referral_not_found", "Referral not found"),
        )
    return rec


async def _get_activity_type(
    session: AsyncSession, tenant_id: str, activity_id: str
) -> "PsychiatricActivityType":
    from app.models.models import PsychiatricActivityType as _AT

    rec = (
        await session.execute(
            select(_AT).where(_AT.id == activity_id, _AT.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("activity_type_not_found", "Psychiatric activity type not found"),
        )
    return rec
