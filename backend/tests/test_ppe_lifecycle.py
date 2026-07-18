"""Pure-logic tests for the PPE issue FSM and personal-card line statuses.

Hermetic: no DB, no route imports (Windows libmagic pitfall).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.ppe.lifecycle import (
    ADMISSION_BLOCKING_STATUSES,
    ISSUE_STATUS_ISSUED,
    ISSUE_STATUS_LOST,
    ISSUE_STATUS_REPLACED,
    ISSUE_STATUS_RETURNED,
    ISSUE_STATUS_WRITTEN_OFF,
    IssueView,
    PPETransitionError,
    card_line_status,
    fold_card_status,
    match_issues_for_norm_line,
    norm_line_key,
    validate_transition,
)

TODAY = date(2026, 6, 10)


# --- FSM -------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        ISSUE_STATUS_RETURNED,
        ISSUE_STATUS_WRITTEN_OFF,
        ISSUE_STATUS_REPLACED,
        ISSUE_STATUS_LOST,
    ],
)
def test_issued_can_transition_to_each_terminal(target):
    validate_transition(ISSUE_STATUS_ISSUED, target)  # must not raise


@pytest.mark.parametrize(
    "current",
    [
        ISSUE_STATUS_RETURNED,
        ISSUE_STATUS_WRITTEN_OFF,
        ISSUE_STATUS_REPLACED,
        ISSUE_STATUS_LOST,
    ],
)
def test_terminal_statuses_are_frozen(current):
    with pytest.raises(PPETransitionError):
        validate_transition(current, ISSUE_STATUS_RETURNED)


def test_unknown_status_rejected():
    with pytest.raises(PPETransitionError):
        validate_transition(ISSUE_STATUS_ISSUED, "evaporated")
    with pytest.raises(PPETransitionError):
        validate_transition("bogus", ISSUE_STATUS_RETURNED)


def test_noop_same_status_rejected():
    with pytest.raises(PPETransitionError):
        validate_transition(ISSUE_STATUS_ISSUED, ISSUE_STATUS_ISSUED)


# --- card_line_status ------------------------------------------------------


def _issue(qty=1, expires_in_days: int | None = 100, status=ISSUE_STATUS_ISSUED):
    expires = TODAY + timedelta(days=expires_in_days) if expires_in_days is not None else None
    return IssueView(quantity=qty, expires_at=expires, status=status)


def test_no_active_issues_is_missing():
    assert card_line_status(1, [], TODAY) == "missing"
    # returned-only is not active
    assert card_line_status(1, [_issue(status=ISSUE_STATUS_RETURNED)], TODAY) == "missing"


def test_partial_quantity_is_missing():
    assert card_line_status(2, [_issue(qty=1)], TODAY) == "missing"


def test_expired_active_issue_is_overdue():
    assert card_line_status(1, [_issue(expires_in_days=-1)], TODAY) == "overdue"


def test_due_soon_within_default_30_days():
    assert card_line_status(1, [_issue(expires_in_days=10)], TODAY) == "due_soon"


def test_ok_when_far_from_expiry():
    assert card_line_status(1, [_issue(expires_in_days=200)], TODAY) == "ok"


def test_termless_issue_is_ok():
    # expires_at IS NULL → бессрочно
    assert card_line_status(1, [_issue(expires_in_days=None)], TODAY) == "ok"


def test_overdue_beats_due_soon_within_line():
    issues = [_issue(expires_in_days=10), _issue(expires_in_days=-5)]
    assert card_line_status(1, issues, TODAY) == "overdue"


# --- fold_card_status ------------------------------------------------------


def test_fold_empty_is_ok():
    assert fold_card_status([]) == "ok"


def test_fold_worst_of():
    assert fold_card_status(["ok", "due_soon"]) == "due_soon"
    assert fold_card_status(["ok", "overdue", "due_soon"]) == "overdue"
    assert fold_card_status(["missing", "overdue"]) == "missing"
    assert fold_card_status(["ok", "ok"]) == "ok"


# --- norm-line matching helpers (shared by card + admission gate) ------------


def test_norm_line_key_prefers_item_id():
    assert norm_line_key("item-1", "Каска") == "item-1"
    assert norm_line_key(None, "Каска") == "name:Каска"


def test_match_union_of_id_and_name_dedupes_by_issue_id():
    v1, v2 = _issue(), _issue(qty=2)
    by_id = {"item-1": [("iss-1", v1)]}
    by_name = {"Каска": [("iss-1", v1), ("iss-2", v2)]}
    views = match_issues_for_norm_line("item-1", "Каска", by_id, by_name)
    assert len(views) == 2  # iss-1 deduped, iss-2 added by name


def test_match_name_only_norm_ignores_id_index():
    v = _issue()
    views = match_issues_for_norm_line(
        None, "Каска", {"item-1": [("iss-1", v)]}, {"Каска": [("iss-1", v)]}
    )
    assert views == [v]


def test_match_no_hits_is_empty():
    assert match_issues_for_norm_line("item-x", "Нет такого", {}, {}) == []


def test_admission_blocking_statuses_contract():
    assert ADMISSION_BLOCKING_STATUSES == frozenset({"missing", "overdue"})
