from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TemplateCreateRequest(BaseModel):
    code: str
    name: str
    description: str | None = None


class TemplatePatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    current_version_id: str | None = None
    version: int | None = None


class TemplateDTO(BaseModel):
    id: str
    code: str | None = None
    name: str
    description: str | None = None
    status: str | None = None
    current_version_id: str | None = None
    updated_at: datetime
    created_at: datetime
    version: int


class TemplateVersionDTO(BaseModel):
    id: str
    template_id: str
    version_number: int = Field(alias="version")
    status: str
    sha256: str | None = None
    size_bytes: int | None = None
    file_id: str | None = None
    placeholders_json: dict[str, Any] | None = Field(default=None, alias="placeholder_index")
    linter_report_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class LintRequest(BaseModel):
    sample_schema: dict[str, Any] | None = None
    required_fields: list[str] | None = None


class LintReportDTO(BaseModel):
    found_fields: list[str]
    blocks: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    summary: dict[str, int]


class PreviewRequest(BaseModel):
    data: dict[str, Any]
    render_pdf: bool = False


class PreviewResponse(BaseModel):
    job_id: str
    status: str
    docx_url: str
    pdf_url: str | None = None


class RenderPreviewRequest(BaseModel):
    code: str
    version: int
    data: dict[str, Any]
    visible_passport: bool = True
    npa_binding_id: str | None = None


class RenderPreviewResponse(BaseModel):
    file_id: str
    sha256: str
    passport: dict[str, Any]
    warnings: list[str]
    generated_at: datetime
