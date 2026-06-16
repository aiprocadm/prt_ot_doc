from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field, field_validator

from app.modules.branding.schemas import LetterheadOverride
from app.schemas.base import BaseSchema


class PackListItem(BaseSchema):
    id: str
    code: str
    name: str
    description: str | None = None
    module: str
    scenario_type: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PackListMeta(BaseSchema):
    page: int
    per_page: int
    total: int
    pages: int


class PackListResponse(BaseSchema):
    ok: bool = True
    data: list[PackListItem]
    meta: PackListMeta


class PackScenarioTemplate(BaseSchema):
    code: str
    name: str
    category: str


class PackScenarioDescriptor(BaseSchema):
    code: str
    name: str
    description: str
    scenario: str
    module: str
    scenario_type: str
    templates: list[PackScenarioTemplate]


class PackScenarioListResponse(BaseSchema):
    ok: bool = True
    data: list[PackScenarioDescriptor]


class PackFromScenarioRequest(BaseSchema):
    name: str | None = None
    description: str | None = None
    is_active: bool = True

class PackRunRequest(BaseSchema):
    pack_code: str
    company_id: str
    site_id: str | None = None
    person_ids: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    letterhead: LetterheadOverride | None = None


class PackRunTask(BaseSchema):
    run_id: str
    template_id: str
    template_name: str
    person_id: str | None = None
    task_id: str | None = None
    status: str


class PackRunResponse(BaseSchema):
    batch_id: str
    tasks: list[PackRunTask]


class PackNamingConfig(BaseSchema):
    org: str | None = None
    unit: str | None = None
    project: str | None = None
    client: str | None = None
    topic: str | None = None
    version: int | None = Field(default=None, ge=1, le=99)
    reference_date: date | None = None
    flags: list[str] = Field(default_factory=list)


class PackGenerateRequest(PackRunRequest):
    naming: PackNamingConfig = Field(default_factory=PackNamingConfig)
    include_docx: bool = True
    include_pdf: bool = True


class PackGeneratedDocument(BaseSchema):
    template_id: str
    template_name: str
    person_id: str | None
    basename: str
    docx_storage_key: str | None = None
    pdf_storage_key: str | None = None
    docx_zip_path: str | None = None
    pdf_zip_path: str | None = None


class PackGenerateResponse(BaseSchema):
    zip_storage_key: str
    documents: list[PackGeneratedDocument]

    @field_validator("documents")
    @classmethod
    def _ensure_not_empty(cls, value: list[PackGeneratedDocument]) -> list[PackGeneratedDocument]:
        if not value:
            raise ValueError("documents must not be empty")
        return value
