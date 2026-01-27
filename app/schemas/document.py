from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, Field

from app.models.document import DocumentStatus
from app.schemas.base import BaseSchema


class DocumentStatusUpdate(BaseSchema):
    to: DocumentStatus = Field(validation_alias=AliasChoices("to", "status"))


class DocumentRead(BaseSchema):
    id: str
    company_id: str
    template_id: str
    person_id: str | None = None
    status: DocumentStatus
    storage_key: str | None = None
    created_by: str
    created_at: datetime
    updated_at: datetime


class DocumentBatchItemRead(BaseSchema):
    id: str
    row_index: int
    status: str
    error: str | None = None
    document_id: str | None = None
    document_version_id: str | None = None
    output_name: str | None = None


class DocumentBatchRunRead(BaseSchema):
    id: str
    status: str
    total: int
    processed: int
    succeeded: int
    failed: int
    items: list[DocumentBatchItemRead] = []
