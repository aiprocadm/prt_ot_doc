from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Company, PipelineRun, Site, Tenant
from app.modules.headers.models import HeaderFooterPreset
from app.modules.headers.placeholders import render_placeholders

from .schemas import BrandingProfilePayload, BrandingProfileRead, BrandingResolutionMeta


def assemble_header_context(
    *,
    branding: BrandingProfilePayload,
    company_ref: dict[str, Any],
    site: Site | None,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    branch_name = branding.branch_label or (site.name if site is not None else None)
    return {
        "organization": branding.model_dump(),
        "company": company_ref,
        "branch": {"id": site.id, "name": branch_name, "address": site.address} if site else {},
        "doc": doc or {},
    }


def build_adhoc_context(
    *,
    branding: BrandingProfilePayload,
    doc: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return assemble_header_context(
        branding=branding,
        company_ref={"id": None, "name": branding.legal_name or branding.short_name},
        site=None,
        doc=doc,
    )


class BrandingService:
    def __init__(self, session: AsyncSession, tenant: Tenant) -> None:
        self.session = session
        self.tenant = tenant

    async def get_company(self, company_id: str) -> Company:
        stmt = select(Company).where(
            Company.id == company_id,
            Company.tenant_id == self.tenant.id,
            Company.deleted_at.is_(None),
        )
        company = (await self.session.execute(stmt)).scalar_one_or_none()
        if company is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
        return company

    async def get_site(self, site_id: str | None) -> Site | None:
        if not site_id:
            return None
        stmt = select(Site).where(
            Site.id == site_id, Site.tenant_id == self.tenant.id, Site.deleted_at.is_(None)
        )
        site = (await self.session.execute(stmt)).scalar_one_or_none()
        if site is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Site not found")
        return site

    async def get_layout_preset(self, preset_code: str | None) -> HeaderFooterPreset | None:
        if not preset_code:
            return None
        stmt = select(HeaderFooterPreset).where(
            HeaderFooterPreset.tenant_id == str(self.tenant.id),
            HeaderFooterPreset.code == preset_code,
            HeaderFooterPreset.deleted_at.is_(None),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            elif value not in (None, "", [], {}):
                merged[key] = value
        return merged

    def merge_branding_patch(
        self, current_payload: dict[str, Any] | None, patch_payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._deep_merge(current_payload or {}, patch_payload)

    def _tenant_branding(self) -> dict[str, Any]:
        settings = getattr(self.tenant, "settings", {}) or {}
        return deepcopy(settings.get("branding", {}))

    def _stable_payload_hash(self, payload: dict[str, Any]) -> str:
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _hash_optional_payload(self, payload: Any) -> str | None:
        if payload in (None, "", [], {}):
            return None
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def build_profile(self, *, company: Company, site: Site | None = None) -> BrandingProfileRead:
        tenant_branding = self._tenant_branding()
        payload = tenant_branding
        payload = self._deep_merge(payload, company.branding_payload or {})
        scope = "company"
        if site is not None:
            payload = self._deep_merge(payload, site.branding_payload or {})
            scope = "site"
        payload.setdefault("legal_name", company.name)
        payload.setdefault("short_name", company.name)
        payload.setdefault("inn", company.inn)
        payload.setdefault("kpp", company.kpp)
        payload.setdefault("ogrn", company.ogrn)
        payload.setdefault("legal_address", company.legal_address)
        payload.setdefault("actual_address", company.actual_address)
        payload.setdefault("email", company.email or company.contact_email)
        payload.setdefault(
            "website", company.branding_payload.get("website") if company.branding_payload else None
        )
        payload.setdefault("phones", company.phone_numbers or [])
        payload.setdefault(
            "header_details",
            [
                item
                for item in [
                    payload.get("short_name") or company.name,
                    site.name if site is not None else None,
                    company.legal_address,
                    company.contact_phone,
                    company.email or company.contact_email,
                    payload.get("website"),
                ]
                if item
            ],
        )
        payload.setdefault("images", {})
        payload["images"].setdefault("logo_file_id", company.logo_file_id)
        payload["images"].setdefault("stamp_file_id", company.stamp_file_id)
        payload.setdefault("contacts", [])
        if company.contact_person or company.contact_phone or company.contact_email:
            payload["contacts"] = payload["contacts"] or [
                {
                    "full_name": company.contact_person,
                    "phone": company.contact_phone,
                    "email": company.contact_email,
                    "position": company.director,
                }
            ]
        payload.setdefault(
            "footer_details",
            [
                item
                for item in [
                    company.name,
                    company.inn and f"ИНН {company.inn}",
                    company.kpp and f"КПП {company.kpp}",
                    company.legal_address,
                    company.contact_phone,
                    company.email or company.contact_email,
                ]
                if item
            ],
        )
        if site is not None:
            payload.setdefault("branch_label", site.name)
            if site.address:
                payload.setdefault("service_notes", [site.address])
        branding = BrandingProfilePayload.model_validate(payload)
        header_context = assemble_header_context(
            branding=branding,
            company_ref={"id": company.id, "name": company.name},
            site=site,
            doc={},
        )
        reproducibility = {
            "tenant_id": str(self.tenant.id),
            "company_id": company.id,
            "site_id": site.id if site else None,
            "company_updated_at": (
                company.updated_at.isoformat() if getattr(company, "updated_at", None) else None
            ),
            "site_updated_at": (
                site.updated_at.isoformat() if site and getattr(site, "updated_at", None) else None
            ),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "branding_payload_hash": self._stable_payload_hash(branding.model_dump(mode="json")),
        }
        effective_preset_code = (
            branding.preferred_letterhead_preset
            if site is not None
            else (company.preferred_header_preset_code or branding.preferred_letterhead_preset)
        )
        reproducibility["preferred_header_preset_code"] = effective_preset_code
        resolution = BrandingResolutionMeta(
            scope_chain=["tenant", "company", *(["site"] if site is not None else [])],
            company_has_branding=bool(company.branding_payload),
            site_has_branding=bool(site.branding_payload) if site is not None else False,
            site_branding_applied=site is not None,
            effective_preset_code=effective_preset_code,
            effective_preset_source=(
                "company.preferred_header_preset_code"
                if site is None and company.preferred_header_preset_code
                else (
                    "site.branding.preferred_letterhead_preset"
                    if site is not None
                    and (site.branding_payload or {}).get("preferred_letterhead_preset")
                    else (
                        "company.branding.preferred_letterhead_preset"
                        if (company.branding_payload or {}).get("preferred_letterhead_preset")
                        else (
                            "tenant.settings.branding.preferred_letterhead_preset"
                            if tenant_branding.get("preferred_letterhead_preset")
                            else None
                        )
                    )
                )
            ),
        )
        return BrandingProfileRead(
            company_id=company.id,
            site_id=site.id if site else None,
            scope=scope,
            preferred_header_preset_code=effective_preset_code,
            branding=branding,
            header_context=header_context,
            reproducibility=reproducibility,
            resolution=resolution,
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

    async def render_preview(
        self,
        *,
        company_id: str,
        site_id: str | None,
        preset_code: str | None,
        document_title: str | None,
        document_number: str | None,
        generated_at: str | None,
        watermark_override: dict[str, Any] | None = None,
    ) -> tuple[BrandingProfileRead, HeaderFooterPreset | None, dict[str, str | None], list[str]]:
        company = await self.get_company(company_id)
        site = await self.get_site(site_id)
        profile = self.build_profile(company=company, site=site)
        context = deepcopy(profile.header_context)
        context["doc"] = {
            "title": document_title or "Untitled document",
            "number": document_number or "—",
            "generated_at": generated_at or datetime.now(timezone.utc).date().isoformat(),
            "passport": profile.branding.passport_label
            or f"{company.name} / {document_title or 'document'}",
        }
        effective_preset_code = preset_code or profile.preferred_header_preset_code
        preset = None
        sections = {
            "header_first": None,
            "header_odd": None,
            "header_even": None,
            "footer_first": None,
            "footer_odd": None,
            "footer_even": None,
        }
        unresolved: list[str] = []
        watermark = self.resolve_watermark(
            profile=profile, preset=preset, override=watermark_override
        )
        context["watermark"] = watermark
        if effective_preset_code:
            preset = await self.get_layout_preset(effective_preset_code)
            if preset is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Layout preset not found")
            watermark = self.resolve_watermark(
                profile=profile, preset=preset, override=watermark_override
            )
            context["watermark"] = watermark
            for key in sections:
                raw_value = getattr(preset, f"{key}_xml", None)
                rendered, missing = render_placeholders(raw_value, context, strict=True)
                sections[key] = rendered or None
                unresolved.extend(missing)
        profile.reproducibility["watermark"] = watermark
        profile.reproducibility["rendered_sections_hash"] = self._hash_optional_payload(sections)
        profile.reproducibility["header_context_hash"] = self._hash_optional_payload(context)
        if preset is not None:
            profile.reproducibility["preset_id"] = preset.id
            profile.reproducibility["preset_updated_at"] = (
                preset.updated_at.isoformat() if getattr(preset, "updated_at", None) else None
            )
            profile.reproducibility["preset_content_hash"] = self._hash_optional_payload(
                {
                    "code": preset.code,
                    "different_first": preset.different_first,
                    "different_odd_even": preset.different_odd_even,
                    "header_first_xml": preset.header_first_xml,
                    "header_odd_xml": preset.header_odd_xml,
                    "header_even_xml": preset.header_even_xml,
                    "footer_first_xml": preset.footer_first_xml,
                    "footer_odd_xml": preset.footer_odd_xml,
                    "footer_even_xml": preset.footer_even_xml,
                    "watermark": preset.watermark or {},
                }
            )
            profile.resolution.effective_preset_source = (
                profile.resolution.effective_preset_source or "request_or_profile"
            )
        elif effective_preset_code is None:
            profile.resolution.effective_preset_source = (
                profile.resolution.effective_preset_source or "none"
            )
        return profile, preset, sections, sorted(set(unresolved))

    async def list_generation_history(
        self,
        *,
        company_id: str,
        site_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        await self.get_company(company_id)
        if site_id:
            await self.get_site(site_id)
        stmt = (
            select(PipelineRun)
            .where(PipelineRun.tenant_id == self.tenant.id)
            .order_by(desc(PipelineRun.created_at))
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        history: list[dict[str, Any]] = []
        for row in rows:
            metadata = dict(row.result_metadata or {})
            if metadata.get("company_id") != company_id:
                continue
            branding_meta = dict(metadata.get("branding") or {})
            if site_id is not None and branding_meta.get("site_id") != site_id:
                continue
            if site_id is None and branding_meta.get("site_id") not in (None, ""):
                continue
            history.append(
                {
                    "pipeline_run_id": row.id,
                    "company_id": company_id,
                    "site_id": branding_meta.get("site_id"),
                    "template_id": row.template_id,
                    "template_version_id": row.template_version_id,
                    "status": row.status.value if hasattr(row.status, "value") else str(row.status),
                    "generated_at": (
                        row.created_at.isoformat() if getattr(row, "created_at", None) else None
                    ),
                    "preset_code": branding_meta.get("preset_code"),
                    "document_title": branding_meta.get("document_title"),
                    "document_number": branding_meta.get("document_number"),
                    "output_name": metadata.get("output_name"),
                    "reproducibility": dict(branding_meta.get("reproducibility") or {}),
                }
            )
        return history

    def build_apply_headers_payload(
        self,
        *,
        profile: BrandingProfileRead,
        preset: HeaderFooterPreset | None,
        document_title: str | None,
        document_number: str | None,
        generated_at: str | None,
        watermark_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = deepcopy(profile.header_context)
        context["doc"] = {
            "title": document_title or "Untitled document",
            "number": document_number or "—",
            "generated_at": generated_at or datetime.now(timezone.utc).date().isoformat(),
            "passport": profile.branding.passport_label
            or f"{context['company']['name']} / {document_title or 'document'}",
        }
        context["reproducibility"] = deepcopy(profile.reproducibility)
        return {
            "preset_code": getattr(preset, "code", None) or profile.preferred_header_preset_code,
            "data": context,
            "watermark_override": self.resolve_watermark(
                profile=profile,
                preset=preset,
                override=watermark_override,
            ),
        }
