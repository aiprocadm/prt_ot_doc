from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant, TenantCounter, TenantQuota

router = APIRouter(prefix="/tenancy", tags=["tenancy"])
_AuthDep = Depends(rbac())


@router.get("/context")
async def get_tenancy_context(
    request: Request,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    _: AccessContext = _AuthDep,
) -> dict[str, object]:
    quota = (
        await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
    ).scalar_one_or_none()
    usage = (
        await session.execute(
            select(TenantCounter).where(TenantCounter.tenant_id == tenant.id).order_by(TenantCounter.yyyymm.desc())
        )
    ).scalars().first()
    return {
        "tenant": {
            "id": str(tenant.id),
            "slug": tenant.slug,
            "code": tenant.code,
            "schema_name": tenant.schema_name,
        },
        "quota": quota,
        "usage": usage,
        "correlation_id": getattr(request.state, "trace_id", None),
    }
