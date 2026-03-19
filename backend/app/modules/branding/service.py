
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Company, Site, Tenant
from app.modules.headers.models import HeaderFooterPreset
from app.modules.headers.placeholders import render_placeholders
from .schemas import BrandingProfilePayload, BrandingProfileRead


class BrandingService:
    def __init__(self, session: AsyncSession, tenant: Tenant) -> None:
        self.session = session
        self.tenant = tenant

    async def get_company(self, company_id: str) -> Company:
        stmt = select(Company).where(Company.id == company_id, Company.tenant_id == self.tenant.id, Company.deleted_at.is_(None))
        company = (await self.session.execute(stmt)).scalar_one_or_none()
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
        return company

    async def get_site(self, site_id: str | None) -> Site | None:
        if not site_id:
            return None
        stmt = select(Site).where(Site.id == site_id, Site.tenant_id == self.tenant.id, Site.deleted_at.is_(None))
        site = (await self.session.execute(stmt)).scalar_one_or_none()
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        return site

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            elif value not in (None, "", [], {}):
                merged[key] = value
        return merged

    def _tenant_branding(self) -> dict[str, Any]:
        settings = getattr(self.tenant, 'settings', {}) or {}
        return deepcopy(settings.get('branding', {}))

    def build_profile(self, *, company: Company, site: Site | None = None) -> BrandingProfileRead:
        payload = self._tenant_branding()
        payload = self._deep_merge(payload, company.branding_payload or {})
        scope = 'company'
        if site is not None:
            payload = self._deep_merge(payload, site.branding_payload or {})
            scope = 'site'
        payload.setdefault('legal_name', company.name)
        payload.setdefault('short_name', company.name)
        payload.setdefault('inn', company.inn)
        payload.setdefault('kpp', company.kpp)
        payload.setdefault('ogrn', company.ogrn)
        payload.setdefault('legal_address', company.legal_address)
        payload.setdefault('actual_address', company.actual_address)
        payload.setdefault('email', company.email or company.contact_email)
        payload.setdefault('website', company.branding_payload.get('website') if company.branding_payload else None)
        payload.setdefault('phones', company.phone_numbers or [])
        payload.setdefault('images', {})
        payload['images'].setdefault('logo_file_id', company.logo_file_id)
        payload['images'].setdefault('stamp_file_id', company.stamp_file_id)
        payload.setdefault('contacts', [])
        if company.contact_person or company.contact_phone or company.contact_email:
            payload['contacts'] = payload['contacts'] or [{
                'full_name': company.contact_person,
                'phone': company.contact_phone,
                'email': company.contact_email,
                'position': company.director,
            }]
        payload.setdefault('footer_details', [item for item in [company.name, company.inn and f"ИНН {company.inn}", company.kpp and f"КПП {company.kpp}", company.legal_address, company.contact_phone, company.email or company.contact_email] if item])
        if site is not None:
            payload.setdefault('branch_label', site.name)
            if site.address:
                payload.setdefault('service_notes', [site.address])
        branding = BrandingProfilePayload.model_validate(payload)
        header_context = {
            'organization': branding.model_dump(),
            'company': {'id': company.id, 'name': company.name},
            'branch': {'id': site.id, 'name': site.name, 'address': site.address} if site else {},
            'doc': {},
        }
        reproducibility = {
            'tenant_id': str(self.tenant.id),
            'company_id': company.id,
            'site_id': site.id if site else None,
            'company_updated_at': company.updated_at.isoformat() if getattr(company, 'updated_at', None) else None,
            'site_updated_at': site.updated_at.isoformat() if site and getattr(site, 'updated_at', None) else None,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        effective_preset_code = (
            branding.preferred_letterhead_preset
            if site is not None
            else (company.preferred_header_preset_code or branding.preferred_letterhead_preset)
        )
        reproducibility['preferred_header_preset_code'] = effective_preset_code
        return BrandingProfileRead(
            company_id=company.id,
            site_id=site.id if site else None,
            scope=scope,
            preferred_header_preset_code=effective_preset_code,
            branding=branding,
            header_context=header_context,
            reproducibility=reproducibility,
        )


    def resolve_watermark(
        self,
        *,
        profile: BrandingProfileRead,
        preset: HeaderFooterPreset | None,
        override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        preset_watermark = deepcopy(getattr(preset, "watermark", {}) or {})
        branding_watermark = {
            "enabled": profile.branding.watermark_enabled,
            "text": profile.branding.watermark_text,
        }
        resolved = self._deep_merge(preset_watermark, branding_watermark)
        if override:
            resolved = self._deep_merge(resolved, override)
        if not resolved.get("text"):
            resolved["enabled"] = False
        return resolved

    async def render_preview(self, *, company_id: str, site_id: str | None, preset_code: str | None, document_title: str | None, document_number: str | None, generated_at: str | None, watermark_override: dict[str, Any] | None = None) -> tuple[BrandingProfileRead, HeaderFooterPreset | None, dict[str, str | None], list[str]]:
        company = await self.get_company(company_id)
        site = await self.get_site(site_id)
        profile = self.build_profile(company=company, site=site)
        context = deepcopy(profile.header_context)
        context['doc'] = {
            'title': document_title or 'Untitled document',
            'number': document_number or '—',
            'generated_at': generated_at or datetime.now(timezone.utc).date().isoformat(),
            'passport': profile.branding.passport_label or f"{company.name} / {document_title or 'document'}",
        }
        effective_preset_code = preset_code or profile.preferred_header_preset_code
        preset = None
        sections = {
            'header_first': None,
            'header_odd': None,
            'header_even': None,
            'footer_first': None,
            'footer_odd': None,
            'footer_even': None,
        }
        unresolved: list[str] = []
        watermark = self.resolve_watermark(profile=profile, preset=preset, override=watermark_override)
        if effective_preset_code:
            stmt = select(HeaderFooterPreset).where(HeaderFooterPreset.tenant_id == str(self.tenant.id), HeaderFooterPreset.code == effective_preset_code, HeaderFooterPreset.deleted_at.is_(None))
            preset = (await self.session.execute(stmt)).scalar_one_or_none()
            if preset is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, 'Layout preset not found')
            watermark = self.resolve_watermark(profile=profile, preset=preset, override=watermark_override)
            context['watermark'] = watermark
            for key in sections:
                raw_value = getattr(preset, f'{key}_xml', None)
                rendered, missing = render_placeholders(raw_value, context, strict=True)
                sections[key] = rendered or None
                unresolved.extend(missing)
        profile.reproducibility['watermark'] = watermark
        if preset is not None:
            profile.reproducibility['preset_id'] = preset.id
            profile.reproducibility['preset_updated_at'] = preset.updated_at.isoformat() if getattr(preset, 'updated_at', None) else None
        return profile, preset, sections, sorted(set(unresolved))
