"""Schemas for personal permits (личные допуски)."""

from __future__ import annotations

from datetime import date, datetime

from app.schemas.base import BaseSchema


class PermitCreate(BaseSchema):
    person_id: str
    permit_type: str
    issued_at: date | None = None  # defaults to today in the service layer
    valid_until: date | None = None
    position_id: str | None = None


class PermitUpdate(BaseSchema):
    permit_type: str | None = None
    valid_until: date | None = None
    position_id: str | None = None


class PermitExtend(BaseSchema):
    valid_until: date


class PermitRead(BaseSchema):
    id: str
    person_id: str
    position_id: str | None
    permit_type: str
    issued_at: date
    valid_until: date | None
    status: str
    is_expired: bool
    created_at: datetime
    updated_at: datetime


class PermitPage(BaseSchema):
    items: list[PermitRead]
    total: int
