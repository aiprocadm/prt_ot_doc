"""Pure expiry classification for contractor documents (no I/O).

A document with NO ``valid_until`` is open-ended → OK (not MISSING). This is the
deliberate difference from admission requirements, where a missing deadline means
"required but unknown". Here, absence of an expiry date is a legitimate state.
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.domains.shared import ContingentItemStatus, classify


def document_expiry_status(valid_until: date | None, today: date) -> ContingentItemStatus:
    """Classify a document's expiry. No date → OK (open-ended), else delegate to classify."""
    if valid_until is None:
        return ContingentItemStatus.OK
    return classify(valid_until, today)


class _DocLike(Protocol):
    valid_until: date | None


# Best-first preference: a single OK candidate satisfies; else DUE_SOON; else OVERDUE.
_PREFERENCE = {
    ContingentItemStatus.OK: 0,
    ContingentItemStatus.DUE_SOON: 1,
    ContingentItemStatus.OVERDUE: 2,
}


def best_document(candidates: Sequence[_DocLike], today: date) -> _DocLike | None:
    """The most-OK candidate (OK > DUE_SOON > OVERDUE), or None if there are none."""
    if not candidates:
        return None
    return min(candidates, key=lambda d: _PREFERENCE[document_expiry_status(d.valid_until, today)])


def requirement_status(candidates: Sequence[_DocLike], today: date) -> ContingentItemStatus:
    """Status of a requirement given its satisfying candidates. No candidate → MISSING."""
    best = best_document(candidates, today)
    if best is None:
        return ContingentItemStatus.MISSING
    return document_expiry_status(best.valid_until, today)
