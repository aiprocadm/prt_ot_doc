"""Schemas for admin user role assignments."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
