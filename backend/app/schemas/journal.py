"""Schemas for journals and journal entries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.models.models import JournalType
from app.schemas.base import BaseSchema


class JournalCreate(BaseSchema):
    company_id: str | None = None
    title: str | None = None
    journal_type: JournalType
    started_at: date | None = None
    closed_at: date | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class JournalUpdate(BaseSchema):
    company_id: str | None = None
    title: str | None = None
    journal_type: JournalType | None = None
    started_at: date | None = None
    closed_at: date | None = None
    metadata_json: dict[str, Any] | None = None


class JournalRead(BaseSchema):
    id: str
    company_id: str | None
    title: str | None
    journal_type: JournalType
    started_at: date | None
    closed_at: date | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class JournalPage(BaseSchema):
    items: list[JournalRead]
    total: int


class JournalEntryCreate(BaseSchema):
    journal_id: str | None = None
    person_id: str
    entry_type: JournalType
    entry_date: date | None = None
    instructor: str | None = None
    notes: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class JournalEntryUpdate(BaseSchema):
    journal_id: str | None = None
    person_id: str | None = None
    entry_type: JournalType | None = None
    entry_date: date | None = None
    instructor: str | None = None
    notes: str | None = None
    metadata_json: dict[str, Any] | None = None


class JournalEntryRead(BaseSchema):
    id: str
    journal_id: str
    person_id: str
    entry_type: JournalType
    entry_date: date
    instructor: str | None
    notes: str | None
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class JournalEntryPage(BaseSchema):
    items: list[JournalEntryRead]
    total: int
