"""Schemas for employee attestations and certifications."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.models import AttestationStatus
from app.schemas.base import BaseSchema


class AttestationCreate(BaseSchema):
    person_id: str = Field(min_length=1, max_length=36)
    position_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=255)
    #: Доп. №1 разд. 54.2: область аттестации из закрытого справочника.
    #: Необязательна — у аттестаций других дисциплин её нет.
    area_code: str | None = Field(default=None, max_length=16)
    issued_at: date | None = None
    expires_at: date | None = None
    status: AttestationStatus = AttestationStatus.ACTIVE
    responsible_id: str | None = Field(default=None, min_length=1, max_length=36)
    notes: str | None = None


class AttestationUpdate(BaseSchema):
    person_id: str | None = Field(default=None, min_length=1, max_length=36)
    position_id: str | None = Field(default=None, min_length=1, max_length=36)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    area_code: str | None = Field(default=None, max_length=16)
    issued_at: date | None = None
    expires_at: date | None = None
    status: AttestationStatus | None = None
    responsible_id: str | None = Field(default=None, min_length=1, max_length=36)
    notes: str | None = None


class AttestationRead(BaseSchema):
    id: str
    person_id: str
    position_id: str | None
    name: str
    area_code: str | None = None
    #: область словами — перевод делает сервер, экран его не дублирует
    area_label: str | None = None
    issued_at: date | None
    expires_at: date | None
    status: AttestationStatus
    responsible_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AttestationPage(BaseSchema):
    items: list[AttestationRead]
    total: int
