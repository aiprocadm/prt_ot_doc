from datetime import date

import pytest

from app.domains.permits import lifecycle as lc


def test_status_constants_are_lowercase_values():
    assert lc.PERMIT_STATUS_ACTIVE == "active"
    assert lc.PERMIT_STATUS_EXPIRED == "expired"
    assert lc.PERMIT_STATUS_REVOKED == "revoked"
    assert lc.PERMIT_STATUSES == frozenset({"active", "expired", "revoked"})


def test_allowed_transitions():
    lc.validate_transition(lc.PERMIT_STATUS_ACTIVE, lc.PERMIT_STATUS_EXPIRED)
    lc.validate_transition(lc.PERMIT_STATUS_ACTIVE, lc.PERMIT_STATUS_REVOKED)
    lc.validate_transition(lc.PERMIT_STATUS_EXPIRED, lc.PERMIT_STATUS_ACTIVE)  # re-validation


def test_unknown_status_rejected():
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_ACTIVE, "draft")     # unknown target
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition("pending", lc.PERMIT_STATUS_ACTIVE)   # unknown current


def test_forbidden_transitions_raise():
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_REVOKED, lc.PERMIT_STATUS_ACTIVE)
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_EXPIRED, lc.PERMIT_STATUS_REVOKED)
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_REVOKED, lc.PERMIT_STATUS_EXPIRED)


def test_is_expired():
    today = date(2026, 6, 15)
    assert lc.is_expired(lc.PERMIT_STATUS_ACTIVE, date(2026, 6, 14), today) is True
    assert lc.is_expired(lc.PERMIT_STATUS_ACTIVE, date(2026, 6, 15), today) is False
    assert lc.is_expired(lc.PERMIT_STATUS_ACTIVE, None, today) is False
    assert lc.is_expired(lc.PERMIT_STATUS_REVOKED, date(2026, 1, 1), today) is False


def test_due_status():
    today = date(2026, 6, 15)
    assert lc.due_status(lc.PERMIT_STATUS_ACTIVE, date(2026, 6, 1), today) == "expired"
    assert lc.due_status(lc.PERMIT_STATUS_ACTIVE, date(2026, 12, 1), today) == "active"
    assert lc.due_status(lc.PERMIT_STATUS_REVOKED, date(2026, 1, 1), today) == "revoked"
