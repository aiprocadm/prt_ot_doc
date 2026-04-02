from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class ApiTokenCreateResponse(BaseModel):
    id: str
    name: str
    scopes: list[str]
    token: str
    expires_at: datetime | None
    created_at: datetime


class ApiTokenRead(BaseModel):
    id: str
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None
    is_revoked: bool
