from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, computed_field

from app.schemas.base import BaseSchema


class TemplateRead(BaseSchema):

    id: str
    name: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    storage_key: str | None = None


class TemplatePage(BaseSchema):
    items: list[TemplateRead]
    total: int


class PipelineRunRead(BaseSchema):

    id: str
    status: str
    context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    docx_storage_key: str | None = None
    pdf_storage_key: str | None = None
    result_s3_key: str | None = None
    result_metadata: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @computed_field(return_type=dict[str, Any])
    def payload(self) -> dict[str, Any]:
        return self.context


class Paginated(BaseSchema):
    items: list[Any]
    total: int
