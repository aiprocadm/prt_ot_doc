import pytest

from app.domains.work_permits import lifecycle as lc


def test_status_constants():
    assert lc.STATUS_DRAFT == "draft"
    assert lc.STATUS_ISSUED == "issued"
    assert lc.WORK_PERMIT_STATUSES == frozenset(
        {"draft", "issued", "suspended", "closed", "cancelled"}
    )


def test_allowed_transitions():
    lc.validate_transition(lc.STATUS_DRAFT, lc.STATUS_ISSUED)
    lc.validate_transition(lc.STATUS_ISSUED, lc.STATUS_SUSPENDED)
    lc.validate_transition(lc.STATUS_SUSPENDED, lc.STATUS_ISSUED)
    lc.validate_transition(lc.STATUS_ISSUED, lc.STATUS_CLOSED)


def test_forbidden_transitions_raise():
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition(lc.STATUS_CLOSED, lc.STATUS_ISSUED)  # terminal
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition(lc.STATUS_DRAFT, lc.STATUS_SUSPENDED)  # not allowed
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition("bogus", lc.STATUS_ISSUED)  # unknown


def test_value_validators():
    assert lc.is_work_type("hot_work") is True
    assert lc.is_work_type("nope") is False
    assert lc.is_member_role("foreman") is True
    assert lc.is_member_role("nope") is False


def test_safety_system_vocabulary():
    from app.domains.work_permits import lifecycle as lc

    assert lc.is_safety_system("fall_arrest") is True
    assert lc.is_safety_system("restraint") is True
    assert lc.is_safety_system("nonsense") is False
    assert lc.SAFETY_SYSTEMS == frozenset(
        {"restraint", "positioning", "fall_arrest", "rescue_evacuation", "access"}
    )


def test_event_types_include_ops_journal():
    from app.domains.work_permits import lifecycle as lc

    assert {"admitted", "member_added", "member_removed"}.issubset(lc.EVENT_TYPES)
    # существующие сохранены
    assert {"issued", "suspended", "resumed", "closed", "cancelled", "extended"}.issubset(
        lc.EVENT_TYPES
    )
