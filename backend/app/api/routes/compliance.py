from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.models.models import ComplianceDeadline, Tenant
from app.modules.compliance_deadlines.services import ComplianceDeadlineService
from app.services.person_scope import employed_record_where

router = APIRouter(prefix="/compliance", tags=["compliance"])

# `/deadlines/recompute` rebuilds tenant-wide compliance deadlines — a privileged,
# side-effectful admin action. Mirror analytics `/recompute` (admin/owner only).
_RECOMPUTE_ROLES = ["admin", "owner"]

# The GET reads expose tenant-wide workforce compliance standing (per-person deadline
# status), so they are gated with the management/HR/specialist read set (mirrors
# branding/analytics MGMT_READ); rank-and-file worker/employee/client roles are excluded.
_READ_ROLES = [
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


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_ReadAccess = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_READ_ROLES,
        action="read compliance deadlines",
    )
)
_RecomputeAccess = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_RECOMPUTE_ROLES,
        action="recompute compliance deadlines",
    )
)


@router.get("/deadlines")
async def list_deadlines(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = _ReadAccess,
):
    items = (
        (
            await session.execute(
                select(ComplianceDeadline)
                .where(
                    ComplianceDeadline.tenant_id == tenant.id,
                    # Уволенный не в счёт (срез-127): снимок сроков строится по
                    # всем удостоверениям арендатора, включая удостоверения
                    # уволенных, — их убирает отбор при чтении, как в календаре.
                    employed_record_where(ComplianceDeadline, tenant.id),
                )
                .order_by(ComplianceDeadline.due_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": items, "total": len(items)}


@router.post("/deadlines/recompute")
@audit_operation("recompute", "compliance_deadline")
async def recompute(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = _RecomputeAccess,
):
    count = await ComplianceDeadlineService().recompute_for_certificates(session, tenant.id)
    return {"created": count}


@router.get("/persons/{person_id}/summary")
async def person_summary(
    person_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = _ReadAccess,
):
    stmt = (
        select(ComplianceDeadline.status, func.count())
        .where(ComplianceDeadline.tenant_id == tenant.id, ComplianceDeadline.person_id == person_id)
        .group_by(ComplianceDeadline.status)
    )
    rows = (await session.execute(stmt)).all()
    return {"person_id": person_id, "statuses": {status: count for status, count in rows}}
