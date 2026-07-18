from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class TemplateScopeDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    level: str = Field(default="tenant", validation_alias=AliasChoices("level", "type"))
    tenant_id: str | None = None
    company_id: str | None = None
    site_id: str | None = None
    label: str | None = None
    applicability: str | None = None


class TemplateCreateRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    code: str
    name: str
    description: str | None = None
    category: str | None = None
    status: str | None = None
    template_type: str | None = None
    scope: TemplateScopeDTO = Field(default_factory=TemplateScopeDTO)


class TemplatePatchRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    code: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    current_version_id: str | None = None
    version: int | None = None
    scope: TemplateScopeDTO | None = None
    template_type: str | None = None


class TemplateDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: str
    code: str | None = None
    name: str
    description: str | None = None
    category: str | None = None
    status: str | None = None
    scope: TemplateScopeDTO = Field(default_factory=TemplateScopeDTO)
    current_version_id: str | None = None
    updated_at: datetime
    created_at: datetime
    version: int
    metadata_json: dict[str, Any] | None = None
    template_type: str | None = None
    current_version: "TemplateVersionDTO | None" = None
    versions: list["TemplateVersionDTO"] = Field(default_factory=list)


class TemplateVersionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
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
    document_type: str | None = None
    applicability_rules: dict[str, Any] | None = None
    output_types: list[str] | None = None
    profile: dict[str, Any] | None = None


class LintRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    sample_schema: dict[str, Any] | None = None
    required_fields: list[str] | None = None


class LintReportDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    found_fields: list[str]
    blocks: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    summary: dict[str, int]
    filters: list[dict[str, Any]] = Field(default_factory=list)
    duplicates: list[dict[str, Any]] = Field(default_factory=list)
    empty_placeholders: list[dict[str, Any]] = Field(default_factory=list)
    undefined_variables: list[str] = Field(default_factory=list)
    unused_variables: list[str] = Field(default_factory=list)


class InspectorRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    available_variables: dict[str, Any] | None = None
    required_fields: list[str] | None = None


class InspectorReportDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    available: list[str]
    used: list[str]
    undefined: list[str]
    unused: list[str]
    required_missing: list[str]
    filters: list[dict[str, Any]]
    unknown_filters: list[str]
    loops: list[dict[str, Any]]
    conditions: list[dict[str, Any]]
    summary: dict[str, int]


class TemplateAuditItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    template_id: str
    template_code: str | None = None
    template_name: str
    tenant_id: str
    version_id: str
    version_number: int
    status: str
    file_key: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    load_error: str | None = None
    severity: str


class TemplateAuditReportDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    summary: dict[str, int]
    items: list[TemplateAuditItemDTO] = Field(default_factory=list)


class TemplateVariableInspectorDTO(BaseModel):
    """Variable Inspector projection: used vs declared variables for a template version."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    used: list[dict[str, Any]]
    loops: list[dict[str, Any]]
    conditions: list[dict[str, Any]]
    declared_required: list[str]
    declared_available: list[str]
    coverage: dict[str, Any]


class PreviewRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    data: dict[str, Any]
    render_pdf: bool = False


class PreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    job_id: str
    status: str
    docx_url: str
    pdf_url: str | None = None


class RenderPreviewRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    code: str
    version: int
    data: dict[str, Any]
    visible_passport: bool = True
    npa_binding_id: str | None = None


class RenderPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    file_id: str
    sha256: str
    passport: dict[str, Any]
    warnings: list[str]
    generated_at: datetime


TemplateDTO.model_rebuild()
