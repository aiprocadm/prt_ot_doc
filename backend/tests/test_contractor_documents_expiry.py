from datetime import date, timedelta

from app.domains.shared import ContingentItemStatus
from app.domains.contractors.documents import document_expiry_status

TODAY = date(2026, 6, 9)


def test_no_valid_until_is_ok():
    # An open-ended document (no expiry) is OK, NOT missing.
    assert document_expiry_status(None, TODAY) == ContingentItemStatus.OK


def test_future_is_ok():
    assert document_expiry_status(TODAY + timedelta(days=90), TODAY) == ContingentItemStatus.OK


def test_within_window_is_due_soon():
    assert document_expiry_status(TODAY + timedelta(days=10), TODAY) == ContingentItemStatus.DUE_SOON


def test_past_is_overdue():
    assert document_expiry_status(TODAY - timedelta(days=1), TODAY) == ContingentItemStatus.OVERDUE
