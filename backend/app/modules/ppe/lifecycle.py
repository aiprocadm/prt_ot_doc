"""Pure PPE lifecycle rules: issue FSM + personal-card line statuses.

No I/O and no sqlalchemy imports — mirrors ``domains/medical/lifecycle.py``
and ``domains/contractors/lifecycle.py``. Status values are the canonical
VARCHAR values stored in ``ppeissue.status`` (lowercase, see migration sz01).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping

from app.domains.shared import ContingentItemStatus, classify

ISSUE_STATUS_ISSUED = "issued"
ISSUE_STATUS_RETURNED = "returned"
ISSUE_STATUS_WRITTEN_OFF = "written_off"
ISSUE_STATUS_REPLACED = "replaced"
ISSUE_STATUS_LOST = "lost"

TERMINAL_STATUSES = frozenset(
    {
        ISSUE_STATUS_RETURNED,
        ISSUE_STATUS_WRITTEN_OFF,
        ISSUE_STATUS_REPLACED,
        ISSUE_STATUS_LOST,
    }
)
ISSUE_STATUSES = frozenset({ISSUE_STATUS_ISSUED}) | TERMINAL_STATUSES

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    ISSUE_STATUS_ISSUED: TERMINAL_STATUSES,
    ISSUE_STATUS_RETURNED: frozenset(),
    ISSUE_STATUS_WRITTEN_OFF: frozenset(),
    ISSUE_STATUS_REPLACED: frozenset(),
    ISSUE_STATUS_LOST: frozenset(),
}


class PPETransitionError(ValueError):
    """Invalid PPE issue status transition (maps to HTTP 409 at the API layer)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid PPE issue transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise PPETransitionError unless current -> target is allowed."""
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise PPETransitionError(current, target)


@dataclass(slots=True)
class IssueView:
    """ORM-free projection of a PPE issue for card computations."""

    quantity: int
    expires_at: date | None
    status: str


# Worst-first severity order for folding line statuses into a card verdict.
_SEVERITY = (
    ContingentItemStatus.MISSING.value,
    ContingentItemStatus.OVERDUE.value,
    ContingentItemStatus.DUE_SOON.value,
    ContingentItemStatus.OK.value,
)


def card_line_status(
    required_qty: int,
    issues: Iterable[IssueView],
    today: date,
    due_soon_days: int = 30,
) -> str:
    """Status of one «положено» card line vs the person's issues.

    missing  — no active issues, or active quantity below the norm (partial)
    overdue  — some active issue is past its wear term
    due_soon — some active issue expires within ``due_soon_days``
    ok       — otherwise; issues without expires_at are termless (never expire)
    """
    active = [i for i in issues if i.status == ISSUE_STATUS_ISSUED]
    if not active:
        return ContingentItemStatus.MISSING.value
    if sum(i.quantity for i in active) < required_qty:
        return ContingentItemStatus.MISSING.value

    statuses = {
        classify(i.expires_at, today, warning_days=due_soon_days).value
        for i in active
        if i.expires_at is not None
    }
    for severity in (_SEVERITY[1], _SEVERITY[2]):  # overdue, then due_soon
        if severity in statuses:
            return severity
    return ContingentItemStatus.OK.value


# Card-line statuses that block person admission (vNext §12 gate):
# ok / due_soon pass, overdue / missing block.
ADMISSION_BLOCKING_STATUSES = frozenset(
    {
        ContingentItemStatus.MISSING.value,
        ContingentItemStatus.OVERDUE.value,
    }
)


def norm_line_key(item_id: str | None, item_name: str) -> str:
    """Stable card-line key for a norm: catalog item id, or name-scoped fallback."""
    return item_id or f"name:{item_name}"


def match_issues_for_norm_line(
    norm_item_id: str | None,
    norm_item_name: str,
    issues_by_id: Mapping[str, Iterable[tuple[str, IssueView]]],
    issues_by_name: Mapping[str, Iterable[tuple[str, IssueView]]],
) -> list[IssueView]:
    """Union of id-matched and name-matched issues, deduped by issue id.

    Covers both legacy directions: norm without ``item_id`` vs catalog issue,
    and norm with ``item_id`` vs legacy issue that predates the catalog link.
    Index values are ``(issue_id, IssueView)`` pairs.
    """
    seen: dict[str, IssueView] = {}
    if norm_item_id:
        for issue_id, view in issues_by_id.get(norm_item_id, ()):
            seen[issue_id] = view
    for issue_id, view in issues_by_name.get(norm_item_name, ()):
        seen.setdefault(issue_id, view)
    return list(seen.values())


def fold_card_status(line_statuses: Iterable[str]) -> str:
    """Worst-of fold of line statuses; an empty card (no norms) is ok."""
    seen = set(line_statuses)
    for severity in _SEVERITY:
        if severity in seen:
            return severity
    return ContingentItemStatus.OK.value
