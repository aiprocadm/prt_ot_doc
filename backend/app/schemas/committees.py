"""Pydantic schemas for committees срез-1/срез-2 (P10-01)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import computed_field

from app.models.committees import (
    CommitteeKind,
    CommitteeMemberRole,
    DecisionTaskStatus,
    MeetingStatus,
    VoteChoice,
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


class MemberDetailRead(BaseSchema):
    id: str
    committee_id: str
    person_id: str
    role: CommitteeMemberRole
    person_fio: str | None = None


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
    held_at: datetime | None = None
    protocol_seq: int | None = None
    protocol_year: int | None = None
    members_total: int | None = None
    present_count: int | None = None
    quorum_met: bool | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field(return_type=str | None)
    @property
    def protocol_no(self) -> str | None:
        if self.protocol_seq is None or self.protocol_year is None:
            return None
        return f"{self.protocol_seq}/{self.protocol_year}"


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


# --- Attendance ---
class AttendanceItem(BaseSchema):
    person_id: str
    present: bool = True


class AttendanceBulkUpdate(BaseSchema):
    items: list[AttendanceItem]


class AttendanceRead(BaseSchema):
    id: str
    meeting_id: str
    person_id: str
    present: bool


# --- Votes ---
class VoteCreate(BaseSchema):
    person_id: str
    choice: VoteChoice


class VoteRead(BaseSchema):
    id: str
    decision_id: str
    person_id: str
    choice: VoteChoice


class DecisionVoteSummary(BaseSchema):
    decision_id: str
    votes_for: int
    votes_against: int
    votes_abstain: int
    outcome: str | None = None  # "carried" | "rejected" | None (no votes yet)
    votes: list[VoteRead]


# --- Protocol journal ---
class ProtocolJournalItem(BaseSchema):
    meeting_id: str
    committee_id: str
    committee_name: str
    protocol_no: str  # "N/YYYY"
    held_at: datetime
    members_total: int | None
    present_count: int | None
    decisions_count: int


class ProtocolJournalPage(BaseSchema):
    items: list[ProtocolJournalItem]
    total: int
    limit: int
    offset: int


# --- Protocol projection ---
class ProtocolDecision(BaseSchema):
    decision: DecisionRead
    tasks: list[DecisionTaskRead]
    votes_for: int = 0
    votes_against: int = 0
    votes_abstain: int = 0
    outcome: str | None = None  # "carried" | "rejected" | None (no votes yet)
    votes: list[VoteRead] = []


class ProtocolRead(BaseSchema):
    meeting: MeetingRead
    decisions: list[ProtocolDecision]
