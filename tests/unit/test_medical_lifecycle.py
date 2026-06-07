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
