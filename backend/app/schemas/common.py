from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, computed_field

from app.schemas.base import BaseSchema


class TemplateRead(BaseSchema):

    id: str
    code: str | None = None
    name: str
    description: str | None = None
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    storage_key: str | None = None

    @computed_field(return_type=str | None)
    def category(self) -> str | None:
        return self.metadata.get("category") if isinstance(self.metadata, dict) else None

    @computed_field(return_type=dict[str, Any])
    def scope(self) -> dict[str, Any]:
        if not isinstance(self.metadata, dict):
            return {"level": "tenant", "company_id": None, "site_id": None, "label": None, "applicability": None}
        scope = self.metadata.get("scope") if isinstance(self.metadata.get("scope"), dict) else {}
        return {
            "level": str(scope.get("level") or "tenant"),
            "company_id": scope.get("company_id"),
            "site_id": scope.get("site_id"),
            "label": scope.get("label"),
            "applicability": scope.get("applicability"),
        }


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
