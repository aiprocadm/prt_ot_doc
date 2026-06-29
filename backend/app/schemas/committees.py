"""Pydantic schemas for committees срез-1 (P10-01)."""

from __future__ import annotations

from datetime import date, datetime

from app.models.committees import (
    CommitteeKind,
    CommitteeMemberRole,
    DecisionTaskStatus,
    MeetingStatus,
)
from app.schemas.base import BaseSchema


# --- Committee ---
class CommitteeCreate(BaseSchema):
    kind: CommitteeKind
    name: str
    description: str | None = None
    is_active: bool = True


class CommitteeUpdate(BaseSchema):
    kind: CommitteeKind | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CommitteeRead(BaseSchema):
    id: str
    kind: CommitteeKind
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CommitteePage(BaseSchema):
    items: list[CommitteeRead]
    total: int
    limit: int
    offset: int


# --- Member ---
class MemberCreate(BaseSchema):
    person_id: str
    role: CommitteeMemberRole = CommitteeMemberRole.MEMBER


class MemberRead(BaseSchema):
    id: str
    committee_id: str
    person_id: str
    role: CommitteeMemberRole


# --- Meeting ---
class MeetingCreate(BaseSchema):
    scheduled_at: datetime
    location: str | None = None


class MeetingStatusUpdate(BaseSchema):
    status: MeetingStatus


class MeetingRead(BaseSchema):
    id: str
    committee_id: str
    scheduled_at: datetime
    location: str | None
    status: MeetingStatus
    created_at: datetime
    updated_at: datetime


class MeetingPage(BaseSchema):
    items: list[MeetingRead]
    total: int
    limit: int
    offset: int


# --- Agenda ---
class AgendaItemCreate(BaseSchema):
    title: str
    seq: int = 1
    presenter_person_id: str | None = None


class AgendaItemRead(BaseSchema):
    id: str
    meeting_id: str
    seq: int
    title: str
    presenter_person_id: str | None


# --- Decision ---
class DecisionCreate(BaseSchema):
    text: str
    agenda_item_id: str | None = None


class DecisionRead(BaseSchema):
    id: str
    meeting_id: str
    agenda_item_id: str | None
    text: str
    decided_at: datetime


# --- Decision task ---
class DecisionTaskCreate(BaseSchema):
    assignee_person_id: str | None = None
    due_date: date | None = None
    evidence_note: str | None = None


class DecisionTaskUpdate(BaseSchema):
    assignee_person_id: str | None = None
    due_date: date | None = None
    status: DecisionTaskStatus | None = None
    evidence_note: str | None = None


class DecisionTaskRead(BaseSchema):
    id: str
    decision_id: str
    assignee_person_id: str | None
    due_date: date | None
    status: DecisionTaskStatus
    evidence_note: str | None
    is_overdue: bool


# --- Protocol projection ---
class ProtocolDecision(BaseSchema):
    decision: DecisionRead
    tasks: list[DecisionTaskRead]


class ProtocolRead(BaseSchema):
    meeting: MeetingRead
    decisions: list[ProtocolDecision]
