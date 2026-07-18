"""Unit: committees срез-2 pure rules (quorum, tally, outcome, numbering, gates)."""

from __future__ import annotations

import pytest

from app.domains.committees.lifecycle import (
    DecisionOutcome,
    MeetingTransitionError,
    decision_outcome,
    ensure_can_vote,
    is_quorum,
    next_protocol_seq,
    tally_votes,
)
from app.models.committees import MeetingStatus, VoteChoice


@pytest.mark.parametrize(
    "total,present,expected",
    [(0, 0, False), (4, 2, False), (4, 3, True), (4, 4, True), (3, 2, True), (1, 1, True)],
)
def test_is_quorum(total, present, expected):
    assert is_quorum(total, present) is expected


def test_tally_votes():
    votes = [VoteChoice.FOR, VoteChoice.FOR, VoteChoice.AGAINST, VoteChoice.ABSTAIN]
    assert tally_votes(votes) == (2, 1, 1)


def test_tally_votes_empty():
    assert tally_votes([]) == (0, 0, 0)


@pytest.mark.parametrize(
    "for_,against,expected",
    [
        (2, 1, DecisionOutcome.CARRIED),
        (1, 1, DecisionOutcome.REJECTED),
        (0, 0, DecisionOutcome.REJECTED),
        (0, 3, DecisionOutcome.REJECTED),
    ],
)
def test_decision_outcome(for_, against, expected):
    assert decision_outcome(for_, against) is expected


def test_next_protocol_seq():
    assert next_protocol_seq([]) == 1
    assert next_protocol_seq([1, 2]) == 3
    assert next_protocol_seq([2, 5, 3]) == 6


def test_ensure_can_vote():
    ensure_can_vote(MeetingStatus.HELD)  # no raise
    with pytest.raises(MeetingTransitionError):
        ensure_can_vote(MeetingStatus.PLANNED)
