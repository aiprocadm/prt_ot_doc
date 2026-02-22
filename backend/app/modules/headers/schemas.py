from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WatermarkSchema(BaseModel):
    enabled: bool = False
    text: str | None = None
    opacity: float | None = None
    angle: int | None = None


class HeaderFooterPresetBase(BaseModel):
    code: str
    name: str
    different_first: bool = False
    different_odd_even: bool = False
    header_first_xml: str | None = None
    header_odd_xml: str | None = None
    header_even_xml: str | None = None
    footer_first_xml: str | None = None
    footer_odd_xml: str | None = None
    footer_even_xml: str | None = None
    watermark: dict[str, Any] = Field(default_factory=dict)


class HeaderFooterPresetCreate(HeaderFooterPresetBase):
    pass


class HeaderFooterPresetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    different_first: bool | None = None
    different_odd_even: bool | None = None
    header_first_xml: str | None = None
    header_odd_xml: str | None = None
    header_even_xml: str | None = None
    footer_first_xml: str | None = None
    footer_odd_xml: str | None = None
    footer_even_xml: str | None = None
    watermark: dict[str, Any] | None = None


class HeaderFooterPresetRead(HeaderFooterPresetBase):
    id: str
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)


class LayoutPresetList(BaseModel):
    items: list[HeaderFooterPresetRead]


class ApplyHeadersRequest(BaseModel):
    preset_code: str
    data: dict[str, Any] | None = None
    watermark_override: dict[str, Any] | None = None


class ApplyHeadersAccepted(BaseModel):
    job_id: str
    step: str = "apply_headers"
