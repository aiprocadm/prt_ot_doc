"""Operational dashboard endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.core.security import AccessContext, rbac
from app.modules.operational_dashboard import OperationalDashboardService

logger = logging.getLogger("app.api.operational_dashboard")
router = APIRouter(prefix="/operational", tags=["operational"])

_OPS_DASHBOARD_ROLES = ["admin", "owner", "hr", "ot_pb_lead", "line_manager", "manager"]


def _tenant_uuid_from_request(request: Request, _access: AccessContext) -> str | None:
    """Operational dashboard alerts are scoped strictly by tenant headers."""
    for key in ("X-Tenant-Id", "x-tenant-id", "x-tenant"):
        raw = request.headers.get(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


@router.get(
    "/dashboard",
    summary="Get operational dashboard with critical alerts",
    status_code=status.HTTP_200_OK,
)
async def get_operational_dashboard(
    request: Request,
    access: AccessContext = Depends(rbac(required_roles=_OPS_DASHBOARD_ROLES)),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """
    Get operational dashboard aggregating all critical alerts.

    Returns:
    - 200 OK: Dashboard data with alerts
    - 400 Bad Request: Missing X-Tenant-Id header
    - 401 Unauthorized: User not authenticated
    - 500 Internal Server Error: Unexpected error

    Alert categories:
    - overdue: Training, medical exams, PPE, SOÚT deadlines
    - blocked_approval: Documents awaiting approval
    - integration_error: Failed 1C/EDO/external API calls (24h window)
    - high_risk: Critical risk assessments
    - unassigned_task: Tasks without owner
    """
    settings = get_settings()

    tenant_id = _tenant_uuid_from_request(request, access)

    if not tenant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Tenant scope required (X-Tenant-Id or x-tenant)"},
        )

    try:
        service = OperationalDashboardService(settings)
        dashboard = await service.get_dashboard(tenant_id=tenant_id, db=db)

        code = status.HTTP_200_OK if dashboard.status == "ok" else status.HTTP_200_OK
        return JSONResponse(status_code=code, content=dashboard.model_dump(mode="json"))
    except Exception as e:
        logger.exception("operational_dashboard.get_dashboard_failed")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "dashboard retrieval failed", "detail": str(e)[:100]},
        )


__all__ = ["router"]
