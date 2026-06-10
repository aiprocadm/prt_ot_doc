from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.domains.shared import ContingentItemStatus
from app.domains.contractors.documents import requirement_status, best_document

TODAY = date(2026, 6, 10)


@dataclass
class _Doc:
    valid_until: date | None
    id: str = "d"
    doc_type: str = "license"


def test_no_candidates_is_missing():
    assert requirement_status([], TODAY) == ContingentItemStatus.MISSING


def test_open_ended_candidate_is_ok():
    assert requirement_status([_Doc(None)], TODAY) == ContingentItemStatus.OK


def test_future_candidate_is_ok():
    assert requirement_status([_Doc(TODAY + timedelta(days=90))], TODAY) == ContingentItemStatus.OK


def test_within_window_is_due_soon():
    assert requirement_status([_Doc(TODAY + timedelta(days=10))], TODAY) == ContingentItemStatus.DUE_SOON


def test_past_is_overdue():
    assert requirement_status([_Doc(TODAY - timedelta(days=1))], TODAY) == ContingentItemStatus.OVERDUE


def test_best_of_multiple_valid_beats_expired():
    docs = [_Doc(TODAY - timedelta(days=5), id="old"), _Doc(TODAY + timedelta(days=90), id="new")]
    assert requirement_status(docs, TODAY) == ContingentItemStatus.OK
    assert best_document(docs, TODAY).id == "new"


def test_best_document_none_when_empty():
    assert best_document([], TODAY) is None
