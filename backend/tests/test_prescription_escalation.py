"""Unit tests for prescription escalation/closure helpers (TZ-3.4-V12-01). App-free."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.prescriptions.lifecycle import closure_rate, is_overdue
from app.models.models import PrescriptionStatus as S

TODAY = date(2026, 5, 31)


@pytest.mark.parametrize(
    "due,status,expected",
    [
        (TODAY - timedelta(days=1), S.OPEN, True),
        (TODAY - timedelta(days=1), S.IN_PROGRESS, True),
        (TODAY - timedelta(days=1), S.COMPLETED, True),  # done-but-unverified, past due => overdue
        (TODAY - timedelta(days=1), S.VERIFIED, False),  # terminal => never overdue
        (TODAY - timedelta(days=1), S.CANCELLED, False),  # terminal => never overdue
        (TODAY, S.OPEN, False),  # due today is not yet past due
        (TODAY + timedelta(days=1), S.OPEN, False),
        (None, S.OPEN, False),  # no deadline => not overdue
    ],
)
def test_is_overdue(due, status, expected) -> None:
    assert is_overdue(due, status, TODAY) is expected


def test_closure_rate_counts_verified_and_completed_over_total() -> None:
    counts = {S.OPEN: 1, S.IN_PROGRESS: 1, S.COMPLETED: 2, S.VERIFIED: 2, S.CANCELLED: 0}
    # closed = completed(2) + verified(2) = 4 ; total = 6
    assert closure_rate(counts) == pytest.approx(4 / 6)


def test_closure_rate_zero_when_empty() -> None:
    assert closure_rate({}) == 0.0
    assert closure_rate({S.OPEN: 0, S.CANCELLED: 0}) == 0.0
