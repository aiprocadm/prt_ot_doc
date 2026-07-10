"""Report-builder API (P10-07 §24.3): datasets / definitions CRUD / preview / run.

За фичефлагом ``report_builder`` (default-off → 404, паттерн medical/_common.py).
RBAC зеркалит ``_REPORT_ROLES`` из routes/reports.py: read/preview/run =
admin/owner/ot_specialist/line_manager; write = admin/owner/ot_specialist.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.report_builder.datasets import DATASETS
from app.modules.report_builder.engine import (
    PREVIEW_LIMIT,
    ReportConfigError,
    run_report,
)
from app.modules.report_builder.schemas import (
    ReportColumnMeta,
    ReportDatasetPage,
    ReportDatasetRead,
    ReportDefinitionCreate,
    ReportDefinitionPage,
    ReportDefinitionRead,
    ReportDefinitionUpdate,
    ReportPreviewIn,
    ReportPreviewOut,
)
from app.modules.report_builder.service import (
    ReportBuilderService,
    ReportDefinitionNotFound,
    ReportNameConflict,
    SystemDefinitionImmutable,
)
from app.services.audit import AuditService

router = APIRouter(prefix="/report-builder", tags=["report-builder"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_READ_ROLES = ["admin", "owner", "ot_specialist", "line_manager"]
_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_READ_ROLES, action="read report-builder")),
]
WriteAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_WRITE_ROLES, action="write report-builder")),
]

_FEATURE_CODE = "report_builder"


async def _require_feature(
    session: SessionDep,
    tenant: TenantDep,
) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="REPORT_BUILDER_DISABLED",
                message="Report builder module is not enabled for this tenant",
                error_type="report_builder",
            ),
        )


FeatureGate = Depends(_require_feature)


def _error(code: str, message: str) -> dict:
    return api_problem_detail(code=code, message=message, error_type="report_builder")


def _audit_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _audit(
    session: AsyncSession,
    request: Request,
    access: AccessContext,
    tenant_id: str,
    *,
    action: str,
    object_id: str,
    details: dict | None = None,
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type="report_definition",
        object_id=object_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _config_error(exc: ReportConfigError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_error(exc.code, exc.message)
    )


@router.get("/datasets", response_model=ReportDatasetPage, dependencies=[FeatureGate])
async def list_datasets(tenant: TenantDep, access: ReadAccess) -> ReportDatasetPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    items = [
        ReportDatasetRead(
            code=spec.code,
            title=spec.title,
            columns=[
                ReportColumnMeta(
                    key=c.key,
                    label=c.label,
                    kind=c.kind,
                    aggregatable=c.aggregatable,
                    enum_values=c.enum_values,
                    ops=list(c.ops),
                )
                for c in spec.columns
            ],
        )
        for spec in DATASETS.values()
    ]
    return ReportDatasetPage(items=items, total=len(items))


@router.get("/definitions", response_model=ReportDefinitionPage, dependencies=[FeatureGate])
async def list_definitions(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await ReportBuilderService(session, str(tenant.id)).list_definitions(
        limit=limit, offset=offset
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[("total", total), ("limit", limit), ("offset", offset)],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return ReportDefinitionPage(
        items=[ReportDefinitionRead.model_validate(r) for r in rows], total=total
    )


@router.post(
    "/definitions",
    response_model=ReportDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_definition(
    request: Request,
    payload: ReportDefinitionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.create_definition(
            name=payload.name,
            description=payload.description,
            dataset_code=payload.dataset_code,
            config_json=payload.config_json,
        )
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    except ReportNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("definition_name_conflict", f"Report name already exists: {payload.name}"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="create", object_id=record.id)
    await session.commit()
    await session.refresh(record)
    return ReportDefinitionRead.model_validate(record)


@router.get(
    "/definitions/{definition_id}",
    response_model=ReportDefinitionRead,
    dependencies=[FeatureGate],
)
async def get_definition(
    definition_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        record = await ReportBuilderService(session, str(tenant.id)).get_definition(definition_id)
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    return ReportDefinitionRead.model_validate(record)


@router.patch(
    "/definitions/{definition_id}",
    response_model=ReportDefinitionRead,
    dependencies=[FeatureGate],
)
async def update_definition(
    request: Request,
    definition_id: str,
    payload: ReportDefinitionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.get_definition(definition_id)
        record = await service.update_definition(record, payload.model_dump(exclude_unset=True))
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    except SystemDefinitionImmutable as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_error("system_definition_immutable", "System templates are immutable"),
        ) from exc
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    except ReportNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("definition_name_conflict", "Report name already exists"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="update", object_id=record.id)
    await session.commit()
    await session.refresh(record)
    return ReportDefinitionRead.model_validate(record)


@router.delete(
    "/definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_definition(
    request: Request,
    definition_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.get_definition(definition_id)
        await service.soft_delete_definition(record)
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    except SystemDefinitionImmutable as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_error("system_definition_immutable", "System templates are immutable"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="delete", object_id=record.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=ReportPreviewOut, dependencies=[FeatureGate])
async def preview_report(
    payload: ReportPreviewIn,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
) -> ReportPreviewOut:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        result = await run_report(
            session,
            tenant_id=str(tenant.id),
            dataset_code=payload.dataset_code,
            config=payload.config_json,
            limit=PREVIEW_LIMIT,
        )
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    return ReportPreviewOut(
        columns=[{"key": c.key, "label": c.label, "kind": c.kind} for c in result.columns],
        rows=result.rows,
        total=result.total,
    )
