"""Schemas for admin user role assignments."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import RoleEnum


class UserListItem(BaseModel):
    """Public-safe user record for admin list views (no secrets)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: RoleEnum
    is_active: bool
    last_login_at: datetime | None = None
    company_id: str | None = None
    created_at: datetime
    updated_at: datetime


class UserListPage(BaseModel):
    items: list[UserListItem]
    total: int


class UserRolesRequest(BaseModel):
    roles: list[str] = Field(default_factory=list, min_length=1)

    model_config = ConfigDict(extra="forbid")


class UserRolesResponse(BaseModel):
    user_id: str
    roles: list[str]

    model_config = ConfigDict(extra="forbid")


class UserAttributesRequest(BaseModel):
    company_ids: list[str] = Field(default_factory=list)
    site_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    contractor_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class UserAttributesResponse(BaseModel):
    user_id: str
    company_ids: list[str] = Field(default_factory=list)
    site_ids: list[str] = Field(default_factory=list)
    project_ids: list[str] = Field(default_factory=list)
    contractor_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")
