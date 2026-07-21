"""Pins for the pure reimbursement FSM (§12.4 срез-2, bg02).

I/O-free counterpart of tests/api/test_budget_reimbursement_service.py: here only
the transition table and the editable-window rule are pinned, the same way
work_permits' lifecycle is pinned apart from its service.
"""

from __future__ import annotations

import pytest

from app.modules.budget import reimbursement_lifecycle as lc


def test_action_targets_cover_every_non_terminal_transition() -> None:
    """Каждый переход таблицы достижим ровно одним action роутера — и наоборот."""
    reachable = {target for targets in lc.ALLOWED_TRANSITIONS.values() for target in targets}
    assert set(lc.ACTION_TARGETS.values()) == reachable
    assert set(lc.ACTION_TARGETS) == {"submit", "approve", "reject", "pay"}


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (lc.STATUS_DRAFT, lc.STATUS_SUBMITTED),
        (lc.STATUS_SUBMITTED, lc.STATUS_APPROVED),
        (lc.STATUS_SUBMITTED, lc.STATUS_REJECTED),
        (lc.STATUS_APPROVED, lc.STATUS_PAID),
    ],
)
def test_validate_transition_allows_the_designed_chain(current: str, target: str) -> None:
    lc.validate_transition(current, target)  # не бросает


@pytest.mark.parametrize(
    ("current", "target"),
    [
        # нельзя перепрыгнуть подачу/решение
        (lc.STATUS_DRAFT, lc.STATUS_APPROVED),
        (lc.STATUS_DRAFT, lc.STATUS_PAID),
        (lc.STATUS_SUBMITTED, lc.STATUS_PAID),
        # терминальные статусы никуда не ведут (пересдача = новая заявка)
        (lc.STATUS_REJECTED, lc.STATUS_SUBMITTED),
        (lc.STATUS_REJECTED, lc.STATUS_APPROVED),
        (lc.STATUS_PAID, lc.STATUS_APPROVED),
        # назад по цепочке тоже нельзя
        (lc.STATUS_SUBMITTED, lc.STATUS_DRAFT),
        (lc.STATUS_APPROVED, lc.STATUS_SUBMITTED),
        # неизвестные статусы — та же ошибка, не KeyError
        ("bogus", lc.STATUS_SUBMITTED),
        (lc.STATUS_DRAFT, "bogus"),
    ],
)
def test_validate_transition_rejects_everything_else(current: str, target: str) -> None:
    with pytest.raises(lc.ReimbursementTransitionError) as exc:
        lc.validate_transition(current, target)
    assert exc.value.current == current
    assert exc.value.target == target


def test_ensure_editable_only_in_draft() -> None:
    lc.ensure_editable(lc.STATUS_DRAFT)  # не бросает
    for status in lc.REIMBURSEMENT_STATUSES - {lc.STATUS_DRAFT}:
        with pytest.raises(lc.ReimbursementTransitionError):
            lc.ensure_editable(status)
