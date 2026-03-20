
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    signatories: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BrandingProfileRead(BaseModel):
    company_id: str
    site_id: str | None = None
    scope: str
    preferred_header_preset_code: str | None = None
    branding: BrandingProfilePayload
    header_context: dict[str, Any]
    reproducibility: dict[str, Any]


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


class BrandingPreviewResponse(BaseModel):
    profile: BrandingProfileRead
    preset_code: str | None = None
    sections: dict[str, str | None]
    unresolved_placeholders: list[str] = Field(default_factory=list)
    watermark: dict[str, Any] = Field(default_factory=dict)
    apply_headers_payload: dict[str, Any] = Field(default_factory=dict)
    wizard_defaults: dict[str, Any] = Field(default_factory=dict)
