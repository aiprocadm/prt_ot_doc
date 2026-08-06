"""Pin: committees срез-1 model shapes (P10-01 / TZ B.17)."""

from __future__ import annotations


def test_committee_table_and_columns() -> None:
    from app.models.committees import Committee

    assert Committee.__tablename__ == "committee"
    cols = set(Committee.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "deleted_at",
        "kind",
        "name",
        "description",
        "is_active",
    } <= cols


def test_meeting_table_and_columns() -> None:
    from app.models.committees import CommitteeMeeting

    assert CommitteeMeeting.__tablename__ == "committee_meeting"
    cols = set(CommitteeMeeting.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "deleted_at",
        "committee_id",
        "scheduled_at",
        "location",
        "status",
    } <= cols


def test_child_tables_and_columns() -> None:
    from app.models.committees import (
        CommitteeAgendaItem,
        CommitteeDecision,
        CommitteeDecisionTask,
        CommitteeMember,
    )

    assert CommitteeMember.__tablename__ == "committee_member"
    assert {"committee_id", "person_id", "role"} <= set(CommitteeMember.__table__.columns.keys())
    assert CommitteeAgendaItem.__tablename__ == "committee_agenda_item"
    assert {"meeting_id", "seq", "title", "presenter_person_id"} <= set(
        CommitteeAgendaItem.__table__.columns.keys()
    )
    assert CommitteeDecision.__tablename__ == "committee_decision"
    assert {"meeting_id", "agenda_item_id", "text", "decided_at"} <= set(
        CommitteeDecision.__table__.columns.keys()
    )
    assert CommitteeDecisionTask.__tablename__ == "committee_decision_task"
    assert {
        "decision_id",
        "assignee_person_id",
        "due_date",
        "status",
        "evidence_note",
    } <= set(CommitteeDecisionTask.__table__.columns.keys())


def test_enums_use_value_labels() -> None:
    from app.models.committees import (
        CommitteeKind,
        CommitteeMemberRole,
        DecisionTaskStatus,
        MeetingStatus,
    )

    assert {m.value for m in CommitteeKind} == {
        "osms",
        "pb",
        "commission_training",
        "commission_investigation",
        "other",
    }
    assert {m.value for m in CommitteeMemberRole} == {"chair", "secretary", "member"}
    assert {m.value for m in MeetingStatus} == {"planned", "held", "cancelled"}
    assert {m.value for m in DecisionTaskStatus} == {"open", "in_progress", "done"}


def test_models_reexported_from_package() -> None:
    from app.models import Committee, CommitteeMeeting  # noqa: F401
