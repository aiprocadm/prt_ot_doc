from __future__ import annotations

from pydantic import BaseModel


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
