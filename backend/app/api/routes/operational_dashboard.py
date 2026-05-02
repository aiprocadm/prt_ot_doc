"""Operational Dashboard (Command Center) endpoints (Phase 2.1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.config import get_settings
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.modules.operational_dashboard.schemas import OperationalDashboardResponse
from app.modules.operational_dashboard.service import OperationalDashboardService
from app.models.tenanting import Tenant

router = APIRouter(prefix="/api/v1/operational", tags=["operational"])

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)

# Allow admin and ot_pb_lead to see operational dashboard
_DASHBOARD_ROLES = ["admin", "owner", "ot_pb_lead", "line_manager"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


DashboardAccess = Depends(
    abac(_tenant_resource_id, required_roles=_DASHBOARD_ROLES, action="read operational dashboard")
)


@router.get("/dashboard", response_model=OperationalDashboardResponse)
async def get_operational_dashboard(
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    _: AccessContext = DashboardAccess,
) -> OperationalDashboardResponse:
    """
    Get comprehensive operational dashboard (Command Center).

    Aggregates critical alerts and metrics from all modules:
    - Overdue tasks and items
    - Documents blocked in approval
    - Critical incidents
    - Unassigned high-priority tasks

    Returns:
    - 200 OK: Dashboard data with aggregated alerts
    - 403 Forbidden: User lacks required role
    - 500 Internal Server Error: Data aggregation failed
    """
    TenantContextValidator.ensure_tenant_context(tenant)

    service = OperationalDashboardService()
    dashboard = await service.get_dashboard(session, str(tenant.id))

    return dashboard
