"""Endpoints for СОУТ — спец. оценка условий труда (P10-04 срез-1, TZ B.10)."""
from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select
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
from app.domains.sout.lifecycle import (
    CampaignTransitionError,
    ensure_campaign_open,
    validate_campaign_transition,
)
from app.domains.medical.service import _load_factor_catalog
from app.domains.sout.service import (
    build_class_history_row,
    build_report,
    history_to_read,
    workplace_to_read,
)
from app.domains.sout.suggestions import (
    build_medical_exam_suggestions,
    build_ppe_norm_suggestions,
)
from app.services.sout_print import (
    PdfRendererUnavailable,
    RenderedDoc,
    render_sout_card,
    render_summary_sheet,
)
from app.services.sout_declaration import (
    build_declaration_projection,
    render_declaration,
)
from app.services.sout_import import (
    ImportValidationError,
    apply_import,
    preview_import,
)
from app.domains.sout.import_report import UnsupportedImportFormat
from app.models.sout import (
    SoutCampaign,
    SoutClassHistory,
    SoutFactor,
    SoutGuarantee,
    SoutWorkplace,
)
from app.models.models import MedicalNorm, PPENorm, Position
from app.models.risk import RiskHazard
from app.models.tenanting import Tenant
from app.schemas.sout import (
    CampaignCreate,
    CampaignPage,
    CampaignRead,
    CampaignReport,
    CampaignStatusUpdate,
    CampaignUpdate,
    ClassHistoryRead,
    DeclarationPreview,
    DeclarationRowRead,
    ImportPreview,
    ImportResult,
    FactorCreate,
    FactorRead,
    FactorUpdate,
    GuaranteeCreate,
    GuaranteeRead,
    NormSuggestions,
    WorkplaceCreate,
    WorkplacePage,
    WorkplaceRead,
    WorkplaceUpdate,
)

router = APIRouter(prefix="/sout", tags=["sout"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_ROLES = ["admin"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]


_FEATURE_CODE = "sout"


def _feature_off() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="SOUT_DISABLED",
            message="SOUT module is not enabled for this tenant",
            error_type="sout",
        ),
    )


async def _require_sout_enabled(session: AsyncSession, tenant: Tenant) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise _feature_off()


def _conflict(exc: CampaignTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="SOUT_TRANSITION_INVALID", message=str(exc), error_type="sout"
        ),
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- tenant-scoped getters (patched in tests) ---
async def _get_campaign(session: AsyncSession, tenant: Tenant, cid: str) -> SoutCampaign:
    row = (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == cid,
                SoutCampaign.tenant_id == tenant.id,
                SoutCampaign.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Campaign")
    return row


async def _get_workplace(session: AsyncSession, tenant: Tenant, wid: str) -> SoutWorkplace:
    row = (
        await session.execute(
            select(SoutWorkplace).where(
                SoutWorkplace.id == wid,
                SoutWorkplace.tenant_id == tenant.id,
                SoutWorkplace.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Workplace")
    return row


async def _get_factor(session: AsyncSession, tenant: Tenant, fid: str) -> SoutFactor:
    row = (
        await session.execute(
            select(SoutFactor).where(
                SoutFactor.id == fid, SoutFactor.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Factor")
    return row


async def _validate_position(session: AsyncSession, tenant: Tenant, pid: str) -> str:
    row = (
        await session.execute(
            select(Position.id).where(
                Position.id == pid,
                Position.tenant_id == tenant.id,
                Position.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Position")
    return pid


async def _validate_hazard(session: AsyncSession, tenant: Tenant, hid: str) -> str:
    row = (
        await session.execute(
            select(RiskHazard.id).where(
                RiskHazard.id == hid, RiskHazard.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Hazard")
    return hid


# --- norm-suggestion loaders (patched in tests) ---
async def _load_workplace_factors(session: AsyncSession, tenant: Tenant, wid: str):
    return list(
        (
            await session.execute(
                select(SoutFactor).where(
                    SoutFactor.workplace_id == wid, SoutFactor.tenant_id == tenant.id
                )
            )
        ).scalars().all()
    )


async def _load_hazard_meta(session: AsyncSession, tenant: Tenant, hazard_ids):
    """Return {hazard_id: (title, medical_factor_code)} for the given ids."""
    if not hazard_ids:
        return {}
    rows = (
        await session.execute(
            select(RiskHazard.id, RiskHazard.title, RiskHazard.medical_factor_code).where(
                RiskHazard.id.in_(hazard_ids), RiskHazard.tenant_id == tenant.id
            )
        )
    ).all()
    return {r[0]: (r[1], r[2]) for r in rows}


async def _load_existing_ppe_pairs(session: AsyncSession, tenant: Tenant, position_id: str):
    rows = (
        await session.execute(
            select(PPENorm.position_id, PPENorm.hazard_id).where(
                PPENorm.tenant_id == tenant.id, PPENorm.position_id == position_id
            )
        )
    ).all()
    return {(r[0], r[1]) for r in rows}


async def _load_medical_inputs(session: AsyncSession, tenant: Tenant, position_id: str):
    """Return (factor_catalog, existing_norm_kinds) for the position."""
    catalog = await _load_factor_catalog(session, tenant_id=str(tenant.id))
    kinds = set(
        (
            await session.execute(
                select(MedicalNorm.exam_kind).where(
                    MedicalNorm.tenant_id == tenant.id,
                    MedicalNorm.position_id == position_id,
                )
            )
        ).scalars().all()
    )
    return catalog, kinds


async def _load_declaration_pairs(session: AsyncSession, tenant: Tenant, cid: str):
    """[(workplace, [factors]), ...] for the campaign, ordered by code."""
    workplaces = list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )
    pairs = []
    for w in workplaces:
        factors = list(
            (
                await session.execute(
                    select(SoutFactor).where(
                        SoutFactor.workplace_id == w.id, SoutFactor.tenant_id == tenant.id
                    )
                )
            ).scalars().all()
        )
        pairs.append((w, factors))
    return pairs


# --- Campaigns ---
@router.get("", response_model=CampaignPage)
async def list_campaigns(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CampaignPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    stmt = (
        select(SoutCampaign)
        .where(SoutCampaign.tenant_id == tenant.id, SoutCampaign.deleted_at.is_(None))
        .order_by(SoutCampaign.name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                SoutCampaign.tenant_id == tenant.id, SoutCampaign.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return CampaignPage(
        items=[CampaignRead.model_validate(c, from_attributes=True) for c in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> CampaignRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = SoutCampaign(
        tenant_id=tenant.id,
        name=payload.name,
        expert_org_name=payload.expert_org_name,
        report_number=payload.report_number,
        report_date=payload.report_date,
        planned_date=payload.planned_date,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return CampaignRead.model_validate(row, from_attributes=True)


@router.get("/{cid}", response_model=CampaignRead)
async def get_campaign(cid: str, tenant: TenantDep, session: SessionDep, access: Access) -> CampaignRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_campaign(session, tenant, cid)
    return CampaignRead.model_validate(row, from_attributes=True)


@router.patch("/{cid}", response_model=CampaignRead)
async def update_campaign(
    cid: str, payload: CampaignUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> CampaignRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_campaign(session, tenant, cid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return CampaignRead.model_validate(row, from_attributes=True)


@router.patch("/{cid}/status", response_model=CampaignRead)
async def update_campaign_status(
    cid: str, payload: CampaignStatusUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> CampaignRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_campaign(session, tenant, cid)
    try:
        validate_campaign_transition(row.status, payload.status)
    except CampaignTransitionError as exc:
        raise _conflict(exc)
    row.status = payload.status
    await session.flush()
    await session.refresh(row)
    return CampaignRead.model_validate(row, from_attributes=True)


# --- Workplaces ---
@router.get("/{cid}/workplaces", response_model=WorkplacePage)
async def list_workplaces(
    cid: str,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> WorkplacePage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    await _get_campaign(session, tenant, cid)
    stmt = (
        select(SoutWorkplace)
        .where(
            SoutWorkplace.campaign_id == cid,
            SoutWorkplace.tenant_id == tenant.id,
            SoutWorkplace.deleted_at.is_(None),
        )
        .order_by(SoutWorkplace.workplace_code.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                SoutWorkplace.campaign_id == cid,
                SoutWorkplace.tenant_id == tenant.id,
                SoutWorkplace.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("cid", cid), ("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return WorkplacePage(
        items=[workplace_to_read(w) for w in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/{cid}/workplaces", response_model=WorkplaceRead, status_code=status.HTTP_201_CREATED)
async def add_workplace(
    cid: str, payload: WorkplaceCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> WorkplaceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    try:
        ensure_campaign_open(campaign.status)
    except CampaignTransitionError as exc:
        raise _conflict(exc)
    if payload.position_id is not None:
        await _validate_position(session, tenant, payload.position_id)
    row = SoutWorkplace(
        tenant_id=tenant.id,
        campaign_id=cid,
        workplace_code=payload.workplace_code,
        position_name=payload.position_name,
        person_id=payload.person_id,
        position_id=payload.position_id,
        assessed_class=payload.assessed_class,
        assessment_date=payload.assessment_date,
        next_assessment_date=payload.next_assessment_date,
    )
    session.add(row)
    await session.flush()
    # Record the initial class assignment (old=None) so the trajectory starts at
    # creation, not at the first later edit.
    history = build_class_history_row(
        tenant_id=tenant.id, workplace_id=row.id,
        old_class=None, new_class=row.assessed_class,
    )
    if history is not None:
        session.add(history)
    await session.refresh(row)
    return workplace_to_read(row)


@router.get("/workplaces/{wid}", response_model=WorkplaceRead)
async def get_workplace(wid: str, tenant: TenantDep, session: SessionDep, access: Access) -> WorkplaceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_workplace(session, tenant, wid)
    return workplace_to_read(row)


@router.patch("/workplaces/{wid}", response_model=WorkplaceRead)
async def update_workplace(
    wid: str, payload: WorkplaceUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> WorkplaceRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_workplace(session, tenant, wid)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("position_id") is not None:
        await _validate_position(session, tenant, changes["position_id"])
    old_class = row.assessed_class
    for field, value in changes.items():
        setattr(row, field, value)
    if "assessed_class" in changes:
        history = build_class_history_row(
            tenant_id=tenant.id, workplace_id=row.id,
            old_class=old_class, new_class=row.assessed_class,
        )
        if history is not None:
            session.add(history)
    await session.flush()
    await session.refresh(row)
    return workplace_to_read(row)


@router.get("/workplaces/{wid}/class-history", response_model=list[ClassHistoryRead])
async def list_class_history(
    wid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[ClassHistoryRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    await _get_workplace(session, tenant, wid)
    rows = list(
        (
            await session.execute(
                select(SoutClassHistory)
                .where(
                    SoutClassHistory.workplace_id == wid,
                    SoutClassHistory.tenant_id == tenant.id,
                )
                .order_by(SoutClassHistory.changed_at.asc())
            )
        ).scalars().all()
    )
    return [history_to_read(r) for r in rows]


@router.get("/workplaces/{wid}/norm-suggestions", response_model=NormSuggestions)
async def get_norm_suggestions(
    wid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> NormSuggestions:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    wp = await _get_workplace(session, tenant, wid)
    if wp.position_id is None:
        return NormSuggestions(ppe=[], medical=[])
    factors = await _load_workplace_factors(session, tenant, wid)
    hazard_ids = {f.hazard_id for f in factors if f.hazard_id is not None}
    hazard_meta = await _load_hazard_meta(session, tenant, hazard_ids)
    hazard_titles = {hid: meta[0] for hid, meta in hazard_meta.items()}
    ppe_pairs = await _load_existing_ppe_pairs(session, tenant, wp.position_id)
    ppe = build_ppe_norm_suggestions(
        position_id=wp.position_id,
        factors=factors,
        hazard_titles=hazard_titles,
        existing_norm_pairs=ppe_pairs,
    )
    factor_codes = {meta[1] for meta in hazard_meta.values() if meta[1]}
    catalog, existing_kinds = await _load_medical_inputs(session, tenant, wp.position_id)
    medical = build_medical_exam_suggestions(
        position_id=wp.position_id,
        hazard_factor_codes=factor_codes,
        factor_catalog=catalog,
        existing_norm_kinds=existing_kinds,
    )
    return NormSuggestions(ppe=ppe, medical=medical)


# --- Factors ---
@router.post("/workplaces/{wid}/factors", response_model=FactorRead, status_code=status.HTTP_201_CREATED)
async def add_factor(
    wid: str, payload: FactorCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> FactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    await _get_workplace(session, tenant, wid)
    if payload.hazard_id is not None:
        await _validate_hazard(session, tenant, payload.hazard_id)
    row = SoutFactor(
        tenant_id=tenant.id,
        workplace_id=wid,
        code=payload.code,
        name=payload.name,
        measured_class=payload.measured_class,
        hazard_id=payload.hazard_id,
        note=payload.note,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return FactorRead.model_validate(row, from_attributes=True)


@router.patch("/factors/{fid}", response_model=FactorRead)
async def update_factor(
    fid: str, payload: FactorUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> FactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    row = await _get_factor(session, tenant, fid)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("hazard_id") is not None:
        await _validate_hazard(session, tenant, changes["hazard_id"])
    for field, value in changes.items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return FactorRead.model_validate(row, from_attributes=True)


# --- Guarantees ---
@router.post("/workplaces/{wid}/guarantees", response_model=GuaranteeRead, status_code=status.HTTP_201_CREATED)
async def add_guarantee(
    wid: str, payload: GuaranteeCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> GuaranteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    await _get_workplace(session, tenant, wid)
    row = SoutGuarantee(
        tenant_id=tenant.id,
        workplace_id=wid,
        kind=payload.kind,
        detail=payload.detail,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return GuaranteeRead.model_validate(row, from_attributes=True)


# --- Report projection ---
@router.get("/{cid}/report", response_model=CampaignReport)
async def get_report(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> CampaignReport:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    workplaces = list(
        (
            await session.execute(
                select(SoutWorkplace)
                .where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
                .order_by(SoutWorkplace.workplace_code.asc())
            )
        ).scalars().all()
    )
    triples = []
    for w in workplaces:
        factors = list(
            (
                await session.execute(
                    select(SoutFactor).where(
                        SoutFactor.workplace_id == w.id,
                        SoutFactor.tenant_id == tenant.id,
                    )
                )
            ).scalars().all()
        )
        guarantees = list(
            (
                await session.execute(
                    select(SoutGuarantee).where(
                        SoutGuarantee.workplace_id == w.id,
                        SoutGuarantee.tenant_id == tenant.id,
                    )
                )
            ).scalars().all()
        )
        triples.append((w, factors, guarantees))
    return build_report(campaign, triples)


# --- Printable forms (срез-4а) ---
def _pdf_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=api_problem_detail(
            code="SOUT_PDF_RENDERER_UNAVAILABLE",
            message="PDF converter is unavailable",
            error_type="sout",
        ),
    )


def _doc_response(rendered: RenderedDoc) -> Response:
    encoded_name = quote(rendered.filename, safe="")
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/workplaces/{wid}/card/print")
async def print_sout_card(
    wid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_sout_card(session, tenant=tenant, workplace_id=wid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Workplace")
    return _doc_response(rendered)


@router.get("/{cid}/summary/print")
async def print_summary_sheet(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_summary_sheet(session, tenant=tenant, campaign_id=cid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Campaign")
    return _doc_response(rendered)


@router.get("/{cid}/declaration", response_model=DeclarationPreview)
async def get_declaration(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> DeclarationPreview:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    pairs = await _load_declaration_pairs(session, tenant, cid)
    rows = build_declaration_projection(campaign=campaign, workplaces_with_factors=pairs)
    eligible = [DeclarationRowRead.model_validate(r, from_attributes=True) for r in rows if r.eligible]
    ineligible = [DeclarationRowRead.model_validate(r, from_attributes=True) for r in rows if not r.eligible]
    return DeclarationPreview(
        campaign_id=cid,
        campaign_name=campaign.name,
        eligible=eligible,
        ineligible=ineligible,
        eligible_count=len(eligible),
        ineligible_count=len(ineligible),
    )


@router.get("/{cid}/declaration/print")
async def print_declaration(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    try:
        rendered = await render_declaration(session, tenant=tenant, campaign_id=cid, fmt=fmt)
    except PdfRendererUnavailable as exc:
        raise _pdf_unavailable() from exc
    if rendered is None:
        raise _not_found("Campaign")
    return _doc_response(rendered)


def _unsupported_format(exc: UnsupportedImportFormat) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="SOUT_IMPORT_FORMAT", message=str(exc), error_type="sout"
        ),
    )


def _import_invalid(exc: ImportValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="SOUT_IMPORT_INVALID", message="; ".join(exc.errors), error_type="sout"
        ),
    )


@router.post("/{cid}/import/preview", response_model=ImportPreview)
async def import_preview(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    file: Annotated[UploadFile, File()],
) -> ImportPreview:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    content = await file.read()
    try:
        outcome = await preview_import(
            session, tenant=tenant, campaign_id=cid, content=content, filename=file.filename or ""
        )
    except UnsupportedImportFormat as exc:
        raise _unsupported_format(exc)
    if outcome is None:
        raise _not_found("Campaign")
    return outcome


@router.post("/{cid}/import/apply", response_model=ImportResult)
async def import_apply(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    try:
        ensure_campaign_open(campaign.status)
    except CampaignTransitionError as exc:
        raise _conflict(exc)
    content = await file.read()
    try:
        result = await apply_import(
            session, tenant=tenant, campaign_id=cid, content=content, filename=file.filename or ""
        )
    except UnsupportedImportFormat as exc:
        raise _unsupported_format(exc)
    except ImportValidationError as exc:
        raise _import_invalid(exc)
    if result is None:
        raise _not_found("Campaign")
    return result
