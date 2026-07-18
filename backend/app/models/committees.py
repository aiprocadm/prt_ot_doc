"""Committees / commissions / meetings ORM models (P10-01 срез-1, TZ B.17).

Bounded context kept OUT of the 3000-line ``models.py`` to avoid the
duplicate-class hazards documented there. Native enums use the project
``native_enum`` helper (``.value`` labels, explicit ``name=``) per
enum-pg-label-parity discipline.
"""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class CommitteeKind(str, enum.Enum):
    OSMS = "osms"  # комитет по ОТ
    PB = "pb"  # комитет по ПБ
    COMMISSION_TRAINING = "commission_training"
    COMMISSION_INVESTIGATION = "commission_investigation"
    OTHER = "other"


class CommitteeMemberRole(str, enum.Enum):
    CHAIR = "chair"
    SECRETARY = "secretary"
    MEMBER = "member"


class MeetingStatus(str, enum.Enum):
    PLANNED = "planned"
    HELD = "held"
    CANCELLED = "cancelled"


class DecisionTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class VoteChoice(str, enum.Enum):
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


class Committee(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "committee"

    kind: Mapped[CommitteeKind] = mapped_column(
        native_enum(CommitteeKind, name="committeekind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CommitteeMember(TenantBaseModel):
    __tablename__ = "committee_member"

    committee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[CommitteeMemberRole] = mapped_column(
        native_enum(CommitteeMemberRole, name="committeememberrole"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "committee_id", "person_id", "role", name="uq_committee_member"
        ),
    )


class CommitteeMeeting(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "committee_meeting"

    committee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[MeetingStatus] = mapped_column(
        native_enum(MeetingStatus, name="meetingstatus"),
        nullable=False,
        default=MeetingStatus.PLANNED,
    )
    held_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    protocol_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protocol_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    members_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    present_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quorum_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "committee_id",
            "protocol_year",
            "protocol_seq",
            name="uq_committee_protocol_no",
        ),
    )


class CommitteeAgendaItem(TenantBaseModel):
    __tablename__ = "committee_agenda_item"

    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_meeting.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    presenter_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )


class CommitteeDecision(TenantBaseModel):
    __tablename__ = "committee_decision"

    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_meeting.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agenda_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("committee_agenda_item.id", ondelete="SET NULL"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )


class CommitteeDecisionTask(TenantBaseModel):
    __tablename__ = "committee_decision_task"

    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_decision.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DecisionTaskStatus] = mapped_column(
        native_enum(DecisionTaskStatus, name="decisiontaskstatus"),
        nullable=False,
        default=DecisionTaskStatus.OPEN,
    )
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class CommitteeMeetingAttendance(TenantBaseModel):
    __tablename__ = "committee_meeting_attendance"

    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_meeting.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    present: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "meeting_id", "person_id", name="uq_committee_attendance"),
    )


class CommitteeDecisionVote(TenantBaseModel):
    __tablename__ = "committee_decision_vote"

    decision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("committee_decision.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    person_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    choice: Mapped[VoteChoice] = mapped_column(
        native_enum(VoteChoice, name="votechoice"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "decision_id", "person_id", name="uq_committee_vote"),
    )
