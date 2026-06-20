"""Unit tests for prescription evidence-satisfaction logic (TZ-3.4-V12-01).

Evidence to close (COMPLETED) a prescription may be a textual note OR at least
one attached evidence file. App-free pure-logic tests.
"""
from __future__ import annotations

import pytest

from app.domains.prescriptions.lifecycle import evidence_satisfied


@pytest.mark.parametrize(
    "has_text,file_count,expected",
    [
        (True, 0, True),    # text-only note satisfies (back-compat)
        (False, 1, True),   # a single attached file satisfies
        (True, 2, True),    # both present
        (False, 0, False),  # nothing => not satisfied
    ],
)
def test_evidence_satisfied(has_text: bool, file_count: int, expected: bool) -> None:
    assert evidence_satisfied(has_text=has_text, file_count=file_count) is expected
