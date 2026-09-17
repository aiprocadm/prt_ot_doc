"""Operational dashboard endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.config import get_settings
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, rbac
from app.modules.operational_dashboard import OperationalDashboardService

logger = logging.getLogger("app.api.operational_dashboard")
router = APIRouter(prefix="/operational", tags=["operational"])

# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_OPS_DASHBOARD_ROLES = list(screen_roles("command_center.view"))


def _authenticated_tenant_scope(request: Request, access: AccessContext) -> str | None:
    """Resolve the queried tenant strictly from the authenticated context.

    The tenant scope MUST come from the verified token/user (``AccessContext``),
    never the raw ``X-Tenant-Id`` header — otherwise an authenticated caller of
    tenant A could read tenant B's aggregates by setting the header to a foreign
    tenant id. When a client still supplies an explicit tenant header it must
    match the authenticated tenant (defense-in-depth); a mismatch is rejected
    with 403 rather than silently serving a cross-tenant scope.
    """
    authoritative = access.tenant_id or getattr(access.user, "tenant_id", None)
    if authoritative is None:
        return None
    authoritative = str(authoritative)

    known = {authoritative.lower()}
    if access.tenant_slug:
        known.add(str(access.tenant_slug).strip().lower())
    user_tenant = getattr(access.user, "tenant_id", None)
    if user_tenant:
        known.add(str(user_tenant).lower())

    for key in ("X-Tenant-Id", "x-tenant-id", "x-tenant"):
        raw = request.headers.get(key)
        if raw and str(raw).strip() and str(raw).strip().lower() not in known:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant scope mismatch",
            )
    return authoritative


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

    tenant_id = _authenticated_tenant_scope(request, access)

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
        # Handler returns normally, so the session dependency commits on teardown;
        # an aborted transaction must be rolled back or that commit raises.
        await db.rollback()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "dashboard retrieval failed", "detail": str(e)[:100]},
        )


__all__ = ["router"]
