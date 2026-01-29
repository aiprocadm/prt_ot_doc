"""Schemas for PPE items and issues."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from app.models.models import PPEIssueStatus, PPEItemCategory
from app.schemas.base import BaseSchema


class PPEItemCreate(BaseSchema):
    name: str
    code: str | None = None
    category: PPEItemCategory = PPEItemCategory.OTHER
    description: str | None = None
    default_wear_days: int = Field(default=365, ge=1)
    metadata_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() == "feet":
            return PPEItemCategory.FOOTWEAR
        return value


class PPEItemUpdate(BaseSchema):
    name: str | None = None
    code: str | None = None
    category: PPEItemCategory | None = None
    description: str | None = None
    default_wear_days: int | None = Field(default=None, ge=1)
    metadata_json: dict[str, Any] | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() == "feet":
            return PPEItemCategory.FOOTWEAR
        return value


class PPEItemRead(BaseSchema):
    id: str
    name: str
    code: str | None
    category: PPEItemCategory
    description: str | None
    default_wear_days: int
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PPEItemPage(BaseSchema):
    items: list[PPEItemRead]
    total: int


class PPEIssueCreate(BaseSchema):
    person_id: str
    item_id: str
    quantity: int = Field(default=1, ge=1)
    issued_at: datetime | None = None
    wear_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None


class PPEIssueUpdate(BaseSchema):
    status: PPEIssueStatus | None = None
    returned_at: datetime | None = None
    expires_at: datetime | None = None
    wear_days: int | None = Field(default=None, ge=1)


class PPEIssueRead(BaseSchema):
    id: str
    person_id: str
    item_id: str | None
    item_name: str
    quantity: int
    issued_at: datetime
    expires_at: datetime | None
    returned_at: datetime | None
    wear_days: int | None
    status: PPEIssueStatus
    created_at: datetime
    updated_at: datetime


class PPEIssuePage(BaseSchema):
    items: list[PPEIssueRead]
    total: int
