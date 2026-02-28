from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from datetime import datetime


class UploadInitRequest(BaseModel):
    filename: str
    kind: str
    owner_entity_type: str
    owner_entity_id: str
    tags: list[str] = []


class UploadInitResponse(BaseModel):
    file_id: str
    version_id: str
    upload_url: str
    s3_key: str


class UploadCompleteRequest(BaseModel):
    file_id: str
    version_id: str


class UploadCompleteResponse(BaseModel):
    version_id: str
    status: str
    av_status: str


class DownloadURLResponse(BaseModel):
    url: str
    expires_in: int


class UploadSessionRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    metadata_json: dict[str, Any] | None = None


class UploadSessionResponse(BaseModel):
    file_id: str
    signed_put_url: str
    expires_at: datetime


class FinalizeUploadResponse(BaseModel):
    file_id: str
    status: str


class FileDto(BaseModel):
    id: str
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    av_vendor: str | None
    av_result_json: dict[str, Any]
    metadata_json: dict[str, Any]
    links: list["EntityFileListItem"] = Field(default_factory=list)


class DownloadUrlRequest(BaseModel):
    purpose: str
    ttl_seconds: int = Field(default=600, ge=60, le=3600)


class DownloadUrlResponse(BaseModel):
    signed_get_url: str


class LinkFileRequest(BaseModel):
    entity_type: str
    entity_id: str
    role: str


class EntityFileListItem(BaseModel):
    file_id: str
    role: str
    status: str
    display_name: str
    size: int
