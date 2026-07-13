from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac, rbac
from app.models.models import ComplianceDeadline, Tenant
from app.modules.compliance_deadlines.services import ComplianceDeadlineService

router = APIRouter(prefix="/compliance", tags=["compliance"])
_AuthDep = Depends(rbac())

_COMPLIANCE_READ_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "manager",
    "line_manager",
    "auditor_ro",
]
_COMPLIANCE_WRITE_ROLES = ["admin", "owner", "ot_pb_lead", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ComplianceReadAccess = Depends(
    abac(_tenant_resource_id, required_roles=_COMPLIANCE_READ_ROLES, action="read compliance")
)
ComplianceWriteAccess = Depends(
    abac(_tenant_resource_id, required_roles=_COMPLIANCE_WRITE_ROLES, action="manage compliance")
)


@router.get("/deadlines")
async def list_deadlines(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = _AuthDep,
):
    items = (
        (
            await session.execute(
                select(ComplianceDeadline)
                .where(ComplianceDeadline.tenant_id == tenant.id)
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
    _: AccessContext = ComplianceWriteAccess,
):
    count = await ComplianceDeadlineService().recompute_for_certificates(session, tenant.id)
    return {"created": count}


@router.get("/persons/{person_id}/summary")
async def person_summary(
    person_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = ComplianceReadAccess,
):
    stmt = (
        select(ComplianceDeadline.status, func.count())
        .where(ComplianceDeadline.tenant_id == tenant.id, ComplianceDeadline.person_id == person_id)
        .group_by(ComplianceDeadline.status)
    )
    rows = (await session.execute(stmt)).all()
    return {"person_id": person_id, "statuses": {status: count for status, count in rows}}
