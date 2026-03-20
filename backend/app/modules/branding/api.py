
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from .schemas import BrandingPreviewRequest, BrandingPreviewResponse, BrandingProfilePatch, BrandingProfileRead
from .service import BrandingService

router = APIRouter(prefix="/branding", tags=["branding"])


@router.get("/profile", response_model=BrandingProfileRead)
async def get_branding_profile(company_id: str, site_id: str | None = None, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> BrandingProfileRead:
    service = BrandingService(session, tenant)
    company = await service.get_company(company_id)
    site = await service.get_site(site_id)
    return service.build_profile(company=company, site=site)


@router.patch("/profile/{company_id}", response_model=BrandingProfileRead)
async def update_branding_profile(company_id: str, payload: BrandingProfilePatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> BrandingProfileRead:
    service = BrandingService(session, tenant)
    company = await service.get_company(company_id)
    branding_payload = payload.branding.model_dump(mode='json')
    if payload.preferred_header_preset_code is not None:
        branding_payload['preferred_letterhead_preset'] = payload.preferred_header_preset_code
    if payload.site_id:
        site = await service.get_site(payload.site_id)
        site.branding_payload = branding_payload
    else:
        company.branding_payload = branding_payload
        company.preferred_header_preset_code = payload.preferred_header_preset_code
        site = None
    await session.commit()
    if site is not None:
        await session.refresh(site)
    await session.refresh(company)
    return service.build_profile(company=company, site=site)


@router.post('/preview', response_model=BrandingPreviewResponse)
async def preview_branding(payload: BrandingPreviewRequest, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> BrandingPreviewResponse:
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
        preset_code=getattr(preset, 'code', None),
        sections=sections,
        unresolved_placeholders=unresolved,
        watermark=service.resolve_watermark(profile=profile, preset=preset, override=payload.watermark_override),
        apply_headers_payload=service.build_apply_headers_payload(
            profile=profile,
            preset=preset,
            document_title=payload.document_title,
            document_number=payload.document_number,
            generated_at=payload.generated_at,
            watermark_override=payload.watermark_override,
        ),
        wizard_defaults={
            'company_id': payload.company_id,
            'site_id': payload.site_id,
            'preset_code': getattr(preset, 'code', None) or profile.preferred_header_preset_code,
            'document_title': payload.document_title or 'Untitled document',
            'document_number': payload.document_number or '—',
        },
    )
