from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.branding.schemas import BrandingProfilePayload, IssuerRef, LetterheadOverride
from app.modules.branding.service import BrandingService, build_adhoc_context


@dataclass
class LetterheadDecision:
    apply: bool
    preset: Any = None
    header_context: dict[str, Any] = field(default_factory=dict)
    watermark: dict[str, Any] = field(default_factory=dict)
    issuer_kind: str = "company"
    issuer_id: str | None = None
    preset_code: str | None = None
    branding_payload_hash: str | None = None

    def as_render_log(self) -> dict[str, Any]:
        return {
            "applied": self.apply,
            "issuer_kind": self.issuer_kind,
            "issuer_id": self.issuer_id,
            "preset_code": self.preset_code,
            "branding_payload_hash": self.branding_payload_hash,
        }


class LetterheadResolver:
    """Решает, какой бланк и контекст применить при генерации документа."""

    def __init__(self, branding: BrandingService) -> None:
        self._branding = branding

    async def resolve(
        self,
        *,
        issuer: IssuerRef,
        site_id: str | None,
        doc: dict[str, Any] | None,
        override: LetterheadOverride | None,
    ) -> LetterheadDecision:
        if override is not None and override.disabled:
            return LetterheadDecision(
                apply=False, issuer_kind=issuer.kind, issuer_id=issuer.company_id
            )

        preset_code_override = override.preset_code if override is not None else None

        if issuer.kind == "contractor":
            raise NotImplementedError("contractor issuer is delivered in Slice 2")

        if issuer.kind == "adhoc":
            branding = issuer.inline or BrandingProfilePayload()
            header_context = build_adhoc_context(branding=branding, doc=doc)
            preset = await self._branding.get_layout_preset(preset_code_override)
            if preset is None:
                if preset_code_override:
                    raise ValueError(f"letterhead preset not found: {preset_code_override}")
                return LetterheadDecision(apply=False, issuer_kind="adhoc", issuer_id=None)
            watermark = self._resolve_watermark_for_payload(branding, preset, override)
            return LetterheadDecision(
                apply=True,
                preset=preset,
                header_context=header_context,
                watermark=watermark,
                issuer_kind="adhoc",
                issuer_id=None,
                preset_code=preset.code,
                branding_payload_hash=None,
            )

        # kind == "company"
        company = await self._branding.get_company(issuer.company_id)
        site = await self._branding.get_site(site_id)
        profile = self._branding.build_profile(company=company, site=site)
        if doc:
            profile.header_context = {**profile.header_context, "doc": doc}
        effective_code = preset_code_override or profile.preferred_header_preset_code
        preset = await self._branding.get_layout_preset(effective_code)
        if preset is None:
            if preset_code_override:
                raise ValueError(f"letterhead preset not found: {preset_code_override}")
            return LetterheadDecision(apply=False, issuer_kind="company", issuer_id=company.id)
        watermark = self._branding.resolve_watermark(
            profile=profile,
            preset=preset,
            override=(override.model_dump().get("watermark") if override is not None else None),
        )
        return LetterheadDecision(
            apply=True,
            preset=preset,
            header_context=profile.header_context,
            watermark=watermark,
            issuer_kind="company",
            issuer_id=company.id,
            preset_code=preset.code,
            branding_payload_hash=profile.reproducibility.get("branding_payload_hash"),
        )

    def _resolve_watermark_for_payload(
        self, branding: BrandingProfilePayload, _preset: Any, _override: LetterheadOverride | None
    ) -> dict[str, Any]:
        watermark = {"enabled": bool(branding.watermark_enabled), "text": branding.watermark_text}
        if not watermark.get("text"):
            watermark["enabled"] = False
        return watermark
