"""Read-only endpoints for normative legal acts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_tenant_record
from app.domains.npa.impact import NpaImpactService
from app.models.models import Tenant
from app.models.npa import NpaRevision

from app.api.dependencies import get_session
from app.core.audit_decorator import audit_operation
from app.core.security import rbac
from app.models.npa import NpaAct
from app.schemas.npa import NpaActListResponse, NpaActRead
from app.core.permission_checker import PermissionChecker
from app.core.tenant_validation import TenantContextValidator

router = APIRouter(tags=["npa"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/npa", response_model=NpaActListResponse)
async def list_npa(session: SessionDep, access=Depends(rbac())) -> NpaActListResponse:
    _ = access  # enforce auth
    stmt = select(NpaAct).options(selectinload(NpaAct.clauses)).order_by(NpaAct.code)
    acts = (await session.execute(stmt)).scalars().unique().all()
    return NpaActListResponse(
        items=[NpaActRead.model_validate(act, from_attributes=True) for act in acts]
    )


@router.get("/npa/{act_id}")
async def get_npa_detail(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(rbac()),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    payload = await NpaImpactService(session, str(tenant.id)).detail(act_id, revision_id=revision_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="NPA act not found")
    return payload


@router.post("/npa/{act_id}/impact/tasks")
@audit_operation("create_tasks", "npa_impact")
async def create_npa_update_tasks(
    act_id: str,
    session: SessionDep,
    revision_id: str | None = Query(default=None),
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(rbac()),
) -> dict:
    TenantContextValidator.ensure_tenant_context(tenant)

    tasks = await NpaImpactService(session, str(tenant.id)).create_update_tasks(act_id, getattr(access.user, "id", None), revision_id=revision_id)
    await session.commit()
    return {"created": len(tasks), "items": [{"id": item.id, "title": item.title} for item in tasks]}
