"""Operational dashboard endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import TenantContextValidator, require_auth
from app.db.session import get_db_session
from app.modules.operational_dashboard import OperationalDashboardService

logger = logging.getLogger("app.api.operational_dashboard")
router = APIRouter(prefix="/operational", tags=["operational"])


@router.get(
    "/dashboard",
    summary="Get operational dashboard with critical alerts",
    status_code=status.HTTP_200_OK,
)
async def get_operational_dashboard(
    request: Request,
    current_user = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
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

    tenant_validator = TenantContextValidator(request=request)
    tenant_id = tenant_validator.get_tenant_id()

    if not tenant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "X-Tenant-Id header required"},
        )

    try:
        service = OperationalDashboardService(settings)
        dashboard = await service.get_dashboard(tenant_id=tenant_id, db=db)

        code = (
            status.HTTP_200_OK
            if dashboard.status == "ok"
            else status.HTTP_200_OK
        )
        return JSONResponse(status_code=code, content=dashboard.model_dump())
    except Exception as e:
        logger.exception("operational_dashboard.get_dashboard_failed")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "dashboard retrieval failed", "detail": str(e)[:100]},
        )


__all__ = ["router"]
