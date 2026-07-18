"""Unit: committees срез-2 projections (vote summary, protocol with tally)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.domains.committees.service import build_protocol, vote_summary
from app.models.committees import MeetingStatus, VoteChoice


def _vote(pid, choice):
    return SimpleNamespace(id=f"v-{pid}", decision_id="d1", person_id=pid, choice=choice)


def test_vote_summary_carried():
    votes = [
        _vote("p1", VoteChoice.FOR),
        _vote("p2", VoteChoice.FOR),
        _vote("p3", VoteChoice.AGAINST),
    ]
    s = vote_summary("d1", votes)
    assert (s.votes_for, s.votes_against, s.votes_abstain) == (2, 1, 0)
    assert s.outcome == "carried"


def test_vote_summary_tie_rejected():
    votes = [_vote("p1", VoteChoice.FOR), _vote("p2", VoteChoice.AGAINST)]
    assert vote_summary("d1", votes).outcome == "rejected"


def test_build_protocol_includes_tally():
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    meeting = SimpleNamespace(
        id="m1",
        committee_id="c1",
        scheduled_at=now,
        location=None,
        status=MeetingStatus.HELD,
        held_at=now,
        protocol_seq=1,
        protocol_year=2026,
        members_total=4,
        present_count=3,
        quorum_met=True,
        created_at=now,
        updated_at=now,
    )
    decision = SimpleNamespace(
        id="d1", meeting_id="m1", agenda_item_id=None, text="X", decided_at=now
    )
    votes = [_vote("p1", VoteChoice.FOR), _vote("p2", VoteChoice.FOR)]
    proto = build_protocol(meeting, [(decision, [], votes)])
    pd = proto.decisions[0]
    assert pd.votes_for == 2 and pd.outcome == "carried"
    assert proto.meeting.protocol_seq == 1
