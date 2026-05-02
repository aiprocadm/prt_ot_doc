"""Data quality check endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.core.security import AccessContext, rbac
from app.modules.data_quality import DataQualityService

logger = logging.getLogger("app.api.data_quality")
router = APIRouter(prefix="/data-quality", tags=["data-quality"])

_DQ_READ_ROLES = ["admin", "owner", "hr", "ot_pb_lead", "line_manager"]


def _tenant_uuid_from_request(request: Request, _access: AccessContext) -> str | None:
    """Tenant UUID/subject binding must come from request headers (explicit scope)."""
    for key in ("X-Tenant-Id", "x-tenant-id", "x-tenant"):
        raw = request.headers.get(key)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


@router.get(
    "/report",
    summary="Get comprehensive data quality report",
    status_code=status.HTTP_200_OK,
)
async def get_data_quality_report(
    request: Request,
    access: AccessContext = Depends(rbac(required_roles=_DQ_READ_ROLES)),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """
    Run comprehensive data quality check and return report.

    Returns:
    - 200 OK: Data quality report with issues breakdown
    - 400 Bad Request: Missing X-Tenant-Id header
    - 401 Unauthorized: User not authenticated
    - 500 Internal Server Error: Unexpected error

    Report includes:
    - Data completeness percentage
    - Critical/high/medium/low issue counts
    - Breakdown by issue type (missing fields, broken relationships, expired records, duplicates)
    - Breakdown by entity type (employee, contractor, document, etc.)
    - Top 20 issues with severity and details
    """
    tenant_id = _tenant_uuid_from_request(request, access)

    if not tenant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Missing tenant scope (X-Tenant-Id or x-tenant)"},
        )

    try:
        service = DataQualityService(tenant_id=tenant_id, db=db)
        report = await service.run_comprehensive_check()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=report.model_dump(mode="json"),
        )
    except Exception as e:
        logger.error(f"Error generating data quality report: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Failed to generate data quality report"},
        )


@router.get(
    "/check",
    summary="Run data quality check (backward compatible)",
    status_code=status.HTTP_200_OK,
)
async def check_data_quality(
    request: Request,
    access: AccessContext = Depends(rbac(required_roles=_DQ_READ_ROLES)),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """
    Run data quality check (same as /report, for backward compatibility).

    Returns JSON response with check results.
    """
    tenant_id = _tenant_uuid_from_request(request, access)

    if not tenant_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Missing tenant scope (X-Tenant-Id or x-tenant)"},
        )

    try:
        service = DataQualityService(tenant_id=tenant_id, db=db)
        report = await service.run_comprehensive_check()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=report.model_dump(mode="json"),
        )
    except Exception as e:
        logger.error(f"Error running data quality check: {e}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Failed to run data quality check"},
        )
