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


class DocumentFileLinkRead(BaseSchema):
    id: str
    url: str
    name: str
    mime_type: str
    size: int
    created_at: datetime


class DocumentCompanySummaryRead(BaseSchema):
    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    inn: str
    status: str


class DocumentHistoryEntryRead(BaseSchema):
    id: str
    created_at: datetime
    updated_at: datetime
    document_id: str
    status: str
    storage: DocumentFileLinkRead | None = None
    comment: str | None = None


class DocumentUiRead(BaseSchema):
    id: str
    created_at: datetime
    updated_at: datetime
    name: str
    type: str
    company: DocumentCompanySummaryRead
    status: str
    version: str
    current_version_id: str | None = None
    template_id: str | None = None
    storage: DocumentFileLinkRead | None = None
    history: list[DocumentHistoryEntryRead] = []


class DocumentPaginationRead(BaseSchema):
    page: int
    page_size: int
    total: int


class DocumentUiListResponse(BaseSchema):
    items: list[DocumentUiRead]
    pagination: DocumentPaginationRead


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
