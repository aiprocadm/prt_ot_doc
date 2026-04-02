"""Department schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    company_id: str = Field(..., min_length=1, max_length=36)
    name: str = Field(..., min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class DepartmentUpdate(BaseModel):
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=64)
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class DepartmentRead(BaseModel):
    id: str
    tenant_id: str
    company_id: str
    name: str
    code: str | None = None
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DepartmentPage(BaseModel):
    items: list[DepartmentRead]
    total: int

    model_config = ConfigDict(from_attributes=True)
