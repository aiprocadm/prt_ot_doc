from __future__ import annotations

from datetime import date

import pytest

from app.domains.medical import lifecycle as lc
from app.models.models import MedicalReferralStatus as RS


def test_referral_transitions():
    lc.validate_transition(RS.ISSUED, RS.SCHEDULED)
    lc.validate_transition(RS.SCHEDULED, RS.COMPLETED)
    lc.validate_transition(RS.ISSUED, RS.ISSUED)  # self no-op
    with pytest.raises(lc.InvalidTransition):
        lc.validate_transition(RS.COMPLETED, RS.SCHEDULED)
    with pytest.raises(lc.InvalidTransition):
        lc.validate_transition(RS.ISSUED, RS.COMPLETED)


def test_referral_terminal_and_overdue_and_result():
    assert lc.is_terminal(RS.COMPLETED) and lc.is_terminal(RS.CANCELLED)
    assert not lc.is_terminal(RS.ISSUED)
    assert lc.is_overdue(date(2020, 1, 1), RS.ISSUED, date(2020, 6, 1)) is True
    assert lc.is_overdue(date(2020, 1, 1), RS.COMPLETED, date(2020, 6, 1)) is False
    assert lc.is_overdue(None, RS.ISSUED, date(2020, 6, 1)) is False
    assert lc.requires_result(RS.COMPLETED) is True
    assert lc.requires_result(RS.SCHEDULED) is False


# --- 2.2 periodicity ---


def test_compute_valid_until_and_next_due():
    from app.models.models import MedicalExamKind as K

    assert lc.compute_valid_until(date(2026, 1, 1), 365) == date(2027, 1, 1)
    assert lc.next_due(None, 365, date(2026, 6, 1)) == date(2026, 6, 1)
    assert lc.next_due(date(2026, 1, 1), 365, date(2026, 6, 1)) == date(2027, 1, 1)
    assert lc.interval_for_kind(K.PERIODIC, None) == 365
    assert lc.interval_for_kind(K.PERIODIC, 180) == 180
    assert lc.interval_for_kind(K.PSYCHIATRIC, None) == 1825


# --- 2.3 contingent classification ---


def test_classify_contingent():
    from app.domains.medical.lifecycle import ContingentItemStatus as C

    t = date(2026, 6, 1)
    assert lc.classify(None, t, 30) is C.MISSING
    assert lc.classify(date(2026, 5, 1), t, 30) is C.OVERDUE
    assert lc.classify(date(2026, 6, 15), t, 30) is C.DUE_SOON
    assert lc.classify(date(2027, 1, 1), t, 30) is C.OK


# --- 2.4 required-kinds resolution ---


def test_resolve_required_kinds():
    from app.models.models import MedicalExamKind as K

    norms = [
        ("p1", "h1", None, K.PERIODIC),
        ("p1", None, "3.1", K.PSYCHIATRIC),
        ("p2", "h9", None, K.FLUOROGRAPHY),
    ]
    got = lc.resolve_required_kinds("p1", "3.1", {"h1"}, norms)
    assert got == {K.PERIODIC, K.PSYCHIATRIC}
    assert lc.resolve_required_kinds("p1", "1", set(), norms) == set()
    assert lc.resolve_required_kinds("p2", None, {"h9"}, norms) == {K.FLUOROGRAPHY}


# --- 2.5 suspension rule ---


def test_suspension_rule():
    from app.domains.medical.lifecycle import SuspensionAction as A
    from app.models.models import MedicalFitness as F

    assert lc.requires_suspension(F.UNFIT) is True
    assert lc.requires_suspension(F.FIT) is False
    assert lc.suspension_action(False, F.UNFIT) is A.OPEN
    assert lc.suspension_action(True, F.FIT) is A.LIFT
    assert lc.suspension_action(True, F.FIT_WITH_RESTRICTIONS) is A.LIFT
    assert lc.suspension_action(True, F.UNFIT) is A.NONE
    assert lc.suspension_action(False, F.FIT) is A.NONE


def test_reason_for_exam():
    from app.models.models import MedicalSuspensionReason as Reason

    assert lc.reason_for(["asthma"]) is Reason.CONTRAINDICATION
    assert lc.reason_for([]) is Reason.UNFIT
