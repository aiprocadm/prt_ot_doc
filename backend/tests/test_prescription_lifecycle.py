"""Unit tests for the prescription status FSM (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import pytest

from app.domains.prescriptions.lifecycle import (
    TERMINAL_STATES,
    VERIFY_ROLES,
    InvalidTransition,
    is_terminal,
    requires_evidence,
    validate_transition,
)
from app.models.models import PrescriptionStatus as S


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.IN_PROGRESS),
        (S.OPEN, S.CANCELLED),
        (S.IN_PROGRESS, S.COMPLETED),
        (S.IN_PROGRESS, S.CANCELLED),
        (S.COMPLETED, S.VERIFIED),
        (S.COMPLETED, S.IN_PROGRESS),
    ],
)
def test_allowed_transitions(current, target) -> None:
    validate_transition(current, target)  # must not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.COMPLETED),
        (S.OPEN, S.VERIFIED),
        (S.IN_PROGRESS, S.VERIFIED),
        (S.COMPLETED, S.CANCELLED),
        (S.CANCELLED, S.OPEN),
        (S.VERIFIED, S.IN_PROGRESS),
    ],
)
def test_invalid_transitions_raise(current, target) -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(current, target)


@pytest.mark.parametrize("state", [S.VERIFIED, S.CANCELLED])
def test_terminal_states_reject_all_other_targets(state) -> None:
    for target in S:
        if target == state:
            continue
        with pytest.raises(InvalidTransition):
            validate_transition(state, target)


@pytest.mark.parametrize("state", list(S))
def test_self_transition_is_noop(state) -> None:
    validate_transition(state, state)  # must not raise


def test_terminal_states_constant() -> None:
    assert TERMINAL_STATES == frozenset({S.VERIFIED, S.CANCELLED})


def test_is_terminal() -> None:
    assert is_terminal(S.VERIFIED)
    assert is_terminal(S.CANCELLED)
    assert not is_terminal(S.OPEN)


def test_requires_evidence_only_for_completed() -> None:
    assert requires_evidence(S.COMPLETED)
    for s in (S.OPEN, S.IN_PROGRESS, S.VERIFIED, S.CANCELLED):
        assert not requires_evidence(s)


def test_verify_roles_constant() -> None:
    assert VERIFY_ROLES == frozenset({"admin", "owner"})
