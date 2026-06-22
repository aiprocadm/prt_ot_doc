"""Pure personal-permit (личный допуск) lifecycle rules: FSM + expiry helpers.

No I/O and no sqlalchemy imports — mirrors ``domains/ppe/lifecycle.py``.
Status values are the canonical VARCHAR values stored in ``permit.status``
(lowercase, see migration prm01).
"""

from __future__ import annotations

from datetime import date

PERMIT_STATUS_ACTIVE = "active"
PERMIT_STATUS_EXPIRED = "expired"
PERMIT_STATUS_REVOKED = "revoked"

PERMIT_STATUSES = frozenset(
    {
        PERMIT_STATUS_ACTIVE,
        PERMIT_STATUS_EXPIRED,
        PERMIT_STATUS_REVOKED,
    }
)

# active may expire (by date) or be revoked (manually); an expired permit may be
# re-validated to active via extension; revoked is terminal.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PERMIT_STATUS_ACTIVE: frozenset({PERMIT_STATUS_EXPIRED, PERMIT_STATUS_REVOKED}),
    PERMIT_STATUS_EXPIRED: frozenset({PERMIT_STATUS_ACTIVE}),
    PERMIT_STATUS_REVOKED: frozenset(),
}


class PermitTransitionError(ValueError):
    """Invalid permit status transition (maps to HTTP 409 at the API layer)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid permit transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise PermitTransitionError unless current -> target is an allowed transition.

    An unknown current/target status is rejected as well.
    """
    if current not in PERMIT_STATUSES or target not in PERMIT_STATUSES:
        raise PermitTransitionError(current, target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise PermitTransitionError(current, target)


def is_expired(status: str, valid_until: date | None, today: date) -> bool:
    """True when an active permit is past its valid_until date."""
    return status == PERMIT_STATUS_ACTIVE and valid_until is not None and valid_until < today


def due_status(status: str, valid_until: date | None, today: date) -> str:
    """Target status after applying date-driven expiry (no manual transitions)."""
    if is_expired(status, valid_until, today):
        return PERMIT_STATUS_EXPIRED
    return status
