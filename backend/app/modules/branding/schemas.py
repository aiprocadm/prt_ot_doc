from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrandingContact(BaseModel):
    full_name: str | None = None
    position: str | None = None
    email: str | None = None
    phone: str | None = None


class BrandingImageSet(BaseModel):
    logo_file_id: str | None = None
    stamp_file_id: str | None = None
    signature_file_id: str | None = None


class BrandingPalette(BaseModel):
    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    watermark: str | None = None


class BrandingSignatory(BaseModel):
    full_name: str | None = None
    position: str | None = None
    basis: str | None = None
    signature_file_id: str | None = None
    stamp_file_id: str | None = None


class BrandingResolutionMeta(BaseModel):
    scope_chain: list[str] = Field(default_factory=list)
    company_has_branding: bool = False
    site_has_branding: bool = False
    site_branding_applied: bool = False
    effective_preset_code: str | None = None
    effective_preset_source: str | None = None


class BrandingProfilePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    legal_name: str | None = None
    short_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    website: str | None = None
    email: str | None = None
    phones: list[str] = Field(default_factory=list)
    header_details: list[str] = Field(default_factory=list)
    footer_details: list[str] = Field(default_factory=list)
    service_notes: list[str] = Field(default_factory=list)
    branch_label: str | None = None
    passport_label: str | None = None
    preferred_letterhead_preset: str | None = None
    watermark_text: str | None = None
    watermark_enabled: bool = False
    contacts: list[BrandingContact] = Field(default_factory=list)
    images: BrandingImageSet = Field(default_factory=BrandingImageSet)
    palette: BrandingPalette = Field(default_factory=BrandingPalette)
    signatories: list[BrandingSignatory | dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IssuerRef(BaseModel):
    """Кто выпускает документ (чей бланк). Срез 1: company | adhoc."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["company", "contractor", "adhoc"] = "company"
    company_id: str | None = None
    inline: BrandingProfilePayload | None = None

    @model_validator(mode="after")
    def _check_kind(self) -> "IssuerRef":
        if self.kind == "company" and not self.company_id:
            raise ValueError("company_id is required for issuer kind=company")
        if self.kind == "adhoc":
            if self.inline is None or not self.inline.legal_name:
                raise ValueError("inline.legal_name is required for issuer kind=adhoc")
        return self


class LetterheadOverride(BaseModel):
    """Переопределение бланка в запросе генерации/пакета."""

    model_config = ConfigDict(extra="forbid")

    issuer: IssuerRef | None = None
    preset_code: str | None = None
    disabled: bool = False


class BrandingProfileRead(BaseModel):
    company_id: str
    site_id: str | None = None
    scope: str
    preferred_header_preset_code: str | None = None
    branding: BrandingProfilePayload
    header_context: dict[str, Any]
    reproducibility: dict[str, Any]
    resolution: BrandingResolutionMeta = Field(default_factory=BrandingResolutionMeta)


class BrandingProfilePatch(BaseModel):
    preferred_header_preset_code: str | None = None
    branding: BrandingProfilePayload
    site_id: str | None = None


class BrandingPreviewRequest(BaseModel):
    company_id: str
    site_id: str | None = None
    preset_code: str | None = None
    document_title: str | None = None
    document_number: str | None = None
    generated_at: str | None = None
    watermark_override: dict[str, Any] | None = None


class BrandingGenerationHistoryItem(BaseModel):
    pipeline_run_id: str
    company_id: str
    site_id: str | None = None
    template_id: str | None = None
    template_version_id: str | None = None
    status: str
    generated_at: str | None = None
    preset_code: str | None = None
    document_title: str | None = None
    document_number: str | None = None
    output_name: str | None = None
    reproducibility: dict[str, Any] = Field(default_factory=dict)


class BrandingGenerationHistoryResponse(BaseModel):
    items: list[BrandingGenerationHistoryItem] = Field(default_factory=list)


class BrandingPreviewResponse(BaseModel):
    profile: BrandingProfileRead
    preset_code: str | None = None
    sections: dict[str, str | None]
    unresolved_placeholders: list[str] = Field(default_factory=list)
    watermark: dict[str, Any] = Field(default_factory=dict)
    apply_headers_payload: dict[str, Any] = Field(default_factory=dict)
    wizard_defaults: dict[str, Any] = Field(default_factory=dict)
