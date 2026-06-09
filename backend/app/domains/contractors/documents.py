"""Pure expiry classification for contractor documents (no I/O).

A document with NO ``valid_until`` is open-ended → OK (not MISSING). This is the
deliberate difference from admission requirements, where a missing deadline means
"required but unknown". Here, absence of an expiry date is a legitimate state.
"""
from __future__ import annotations

from datetime import date

from app.domains.shared import ContingentItemStatus, classify


def document_expiry_status(valid_until: date | None, today: date) -> ContingentItemStatus:
    """Classify a document's expiry. No date → OK (open-ended), else delegate to classify."""
    if valid_until is None:
        return ContingentItemStatus.OK
    return classify(valid_until, today)
