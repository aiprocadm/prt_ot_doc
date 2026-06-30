"""Medical endpoints — hazard<->factor mappings, contingent register, prints, summary (ARCH-4 slice 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.routes.medical._common import (
    MedicalAccess,
    MedicalFeatureGate,
    MedicalReadAccess,
    SessionDep,
    TenantDep,
    _error,
    _get_hazard,
    router,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.medical import service as medsvc
from app.models.models import (
    MedicalFactor,
)
from app.models.risk import RiskHazard
from app.schemas.medical import (
    ContingentItem,
    ContingentPage,
    ContingentRegisterPage,
    ContingentRegisterRow,
    HazardFactorMappingIn,
    HazardFactorMappingPage,
    HazardFactorMappingRead,
    MedicalSummary,
    NamedListPage,
    NamedListRow,
)
from app.services.audit import AuditService
from app.services.medical_print import (
    PdfRendererUnavailable,
    render_contingent_register,
    render_named_list,
)


def _mapping_read(hazard: RiskHazard, factor_name: str | None) -> HazardFactorMappingRead:
    return HazardFactorMappingRead(
        hazard_id=hazard.id,
        hazard_code=hazard.code,
        hazard_title=hazard.title,
        factor_code=hazard.medical_factor_code,
        factor_name=factor_name,
    )


@router.get(
    "/medical/hazard-factors",
    response_model=HazardFactorMappingPage,
    dependencies=[MedicalFeatureGate],
)
async def list_hazard_factor_mappings(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> HazardFactorMappingPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    tid = str(tenant.id)
    hazards = list(
        (
            await session.execute(
                select(RiskHazard)
                .where(RiskHazard.tenant_id == tid)
                .order_by(RiskHazard.code.asc())
            )
        )
        .scalars()
        .all()
    )
    codes = {h.medical_factor_code for h in hazards if h.medical_factor_code}
    name_by_code: dict[str, str] = {}
    if codes:
        factors = (
            (
                await session.execute(
                    select(MedicalFactor).where(
                        MedicalFactor.tenant_id == tid,
                        MedicalFactor.code.in_(tuple(codes)),
                    )
                )
            )
            .scalars()
            .all()
        )
        name_by_code = {f.code: f.name for f in factors}
    items = [_mapping_read(h, name_by_code.get(h.medical_factor_code)) for h in hazards]
    return HazardFactorMappingPage(items=items, total=len(items))


@router.put(
    "/medical/hazards/{hazard_id}/factor",
    response_model=HazardFactorMappingRead,
    dependencies=[MedicalFeatureGate],
)
async def set_hazard_factor(
    request: Request,
    hazard_id: str,
    payload: HazardFactorMappingIn,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> HazardFactorMappingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    tid = str(tenant.id)
    hazard = await _get_hazard(session, tid, hazard_id)
    factor_name: str | None = None
    if payload.factor_code is not None:
        factor = (
            await session.execute(
                select(MedicalFactor).where(
                    MedicalFactor.tenant_id == tid,
                    MedicalFactor.code == payload.factor_code,
                )
            )
        ).scalar_one_or_none()
        if factor is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "medical_factor_not_found",
                    f"Unknown factor code: {payload.factor_code}",
                ),
            )
        factor_name = factor.name
    hazard.medical_factor_code = payload.factor_code
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=tid,
        action="update",
        object_type="hazard_factor_mapping",
        object_id=hazard.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(hazard)
    return _mapping_read(hazard, factor_name)


@router.get(
    "/medical/contingent/register",
    response_model=ContingentRegisterPage,
    dependencies=[MedicalFeatureGate],
)
async def get_contingent_register(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> ContingentRegisterPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_contingent_register(session, tenant_id=str(tenant.id), today=today)
    return ContingentRegisterPage(
        items=[ContingentRegisterRow(**r) for r in rows],
        total=len(rows),
    )


@router.get("/medical/named-list", response_model=NamedListPage, dependencies=[MedicalFeatureGate])
async def get_named_list(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> NamedListPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_named_list(session, tenant_id=str(tenant.id), today=today)
    return NamedListPage(items=[NamedListRow(**r) for r in rows], total=len(rows))


async def _render_to_response(coro) -> Response:
    """Awaits a medical render coroutine → file Response (503 если PDF недоступен)."""
    try:
        rendered = await coro
    except PdfRendererUnavailable as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error("pdf_renderer_unavailable", "PDF converter is unavailable"),
        ) from exc
    encoded_name = quote(rendered.filename, safe="")
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/medical/contingent/register/print", dependencies=[MedicalFeatureGate])
async def print_contingent_register(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return await _render_to_response(render_contingent_register(session, tenant=tenant, fmt=fmt))


@router.get("/medical/named-list/print", dependencies=[MedicalFeatureGate])
async def print_named_list(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return await _render_to_response(render_named_list(session, tenant=tenant, fmt=fmt))


# ---------------------------------------------------------------------------
# Task 6.4 — Contingent / generate / summary
# ---------------------------------------------------------------------------


@router.get("/medical/contingent", response_model=ContingentPage, dependencies=[MedicalFeatureGate])
async def get_medical_contingent(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    position_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ContingentPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    items = await medsvc.compute_contingent(
        session,
        tenant_id=str(tenant.id),
        today=today,
        position_id=position_id,
    )
    if status_filter:
        items = [it for it in items if it["status"] == status_filter]
    return ContingentPage(
        items=[ContingentItem(**i) for i in items],
        total=len(items),
    )


@router.post("/medical/contingent/generate-referrals", dependencies=[MedicalFeatureGate])
async def generate_referrals(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    count = await medsvc.generate_due_referrals(
        session,
        tenant_id=str(tenant.id),
        today=today,
        issued_by=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="generate",
        object_type="medical_referral",
        object_id="bulk",
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": count},
    )
    await session.commit()
    return {"count": count}


@router.get("/medical/summary", response_model=MedicalSummary, dependencies=[MedicalFeatureGate])
async def get_medical_summary(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    return MedicalSummary(
        **await medsvc.status_summary(session, tenant_id=str(tenant.id), today=today)
    )
