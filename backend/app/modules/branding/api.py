from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.models.models import Tenant

from .schemas import (
    BrandingGenerationHistoryItem,
    BrandingGenerationHistoryResponse,
    BrandingPreviewRequest,
    BrandingPreviewResponse,
    BrandingProfilePatch,
    BrandingProfileRead,
)
from .service import BrandingService

router = APIRouter(prefix="/branding", tags=["branding"])

_BRANDING_READ_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "manager",
    "line_manager",
    "auditor_ro",
]
_BRANDING_WRITE_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "manager",
]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


BrandingReadAccess = Depends(
    abac(_tenant_resource_id, required_roles=_BRANDING_READ_ROLES, action="read branding")
)
BrandingWriteAccess = Depends(
    abac(_tenant_resource_id, required_roles=_BRANDING_WRITE_ROLES, action="manage branding")
)


@router.get("/profile", response_model=BrandingProfileRead)
async def get_branding_profile(
    company_id: str,
    site_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = BrandingReadAccess,
) -> BrandingProfileRead:
    service = BrandingService(session, tenant)
    company = await service.get_company(company_id)
    site = await service.get_site(site_id)
    return service.build_profile(company=company, site=site)


@router.patch("/profile/{company_id}", response_model=BrandingProfileRead)
async def update_branding_profile(
    company_id: str,
    payload: BrandingProfilePatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = BrandingWriteAccess,
) -> BrandingProfileRead:
    service = BrandingService(session, tenant)
    company = await service.get_company(company_id)
    branding_payload = payload.branding.model_dump(mode="json")
    if payload.preferred_header_preset_code is not None:
        preset = await service.get_layout_preset(payload.preferred_header_preset_code)
        if preset is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Layout preset not found")
        branding_payload["preferred_letterhead_preset"] = preset.code
    if payload.site_id:
        site = await service.get_site(payload.site_id)
        site.branding_payload = service.merge_branding_patch(
            site.branding_payload, branding_payload
        )
    else:
        company.branding_payload = service.merge_branding_patch(
            company.branding_payload, branding_payload
        )
        company.preferred_header_preset_code = payload.preferred_header_preset_code
        site = None
    await session.commit()
    if site is not None:
        await session.refresh(site)
    await session.refresh(company)
    return service.build_profile(company=company, site=site)


@router.get("/history", response_model=BrandingGenerationHistoryResponse)
async def get_branding_history(
    company_id: str,
    site_id: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = BrandingReadAccess,
) -> BrandingGenerationHistoryResponse:
    service = BrandingService(session, tenant)
    items = await service.list_generation_history(
        company_id=company_id, site_id=site_id, limit=limit
    )
    return BrandingGenerationHistoryResponse(
        items=[BrandingGenerationHistoryItem.model_validate(item) for item in items]
    )


@router.post("/preview", response_model=BrandingPreviewResponse)
async def preview_branding(
    payload: BrandingPreviewRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    _: AccessContext = BrandingWriteAccess,
) -> BrandingPreviewResponse:
    service = BrandingService(session, tenant)
    profile, preset, sections, unresolved = await service.render_preview(
        company_id=payload.company_id,
        site_id=payload.site_id,
        preset_code=payload.preset_code,
        document_title=payload.document_title,
        document_number=payload.document_number,
        generated_at=payload.generated_at,
        watermark_override=payload.watermark_override,
    )
    return BrandingPreviewResponse(
        profile=profile,
        preset_code=getattr(preset, "code", None),
        sections=sections,
        unresolved_placeholders=unresolved,
        watermark=service.resolve_watermark(
            profile=profile, preset=preset, override=payload.watermark_override
        ),
        apply_headers_payload=service.build_apply_headers_payload(
            profile=profile,
            preset=preset,
            document_title=payload.document_title,
            document_number=payload.document_number,
            generated_at=payload.generated_at,
            watermark_override=payload.watermark_override,
        ),
        wizard_defaults={
            "company_id": payload.company_id,
            "site_id": payload.site_id,
            "preset_code": getattr(preset, "code", None) or profile.preferred_header_preset_code,
            "document_title": payload.document_title or "Untitled document",
            "document_number": payload.document_number or "—",
        },
    )
