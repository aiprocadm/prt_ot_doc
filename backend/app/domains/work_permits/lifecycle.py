"""Pure work-permit (наряд-допуск) lifecycle rules: FSM + value vocabularies.

No I/O / no sqlalchemy imports — mirrors ``domains/permits/lifecycle.py``.
All values are the canonical VARCHAR strings stored in the DB (see migration wp01).
"""
from __future__ import annotations

STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"
STATUS_SUSPENDED = "suspended"
STATUS_CLOSED = "closed"
STATUS_CANCELLED = "cancelled"

WORK_PERMIT_STATUSES = frozenset({
    STATUS_DRAFT, STATUS_ISSUED, STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED,
})

# огневые / газоопасные / на высоте / замкнутое пространство / земляные / электро
WORK_TYPES = frozenset({
    "hot_work", "gas_hazardous", "height", "confined_space", "excavation", "electrical",
})

# выдающий наряд / ответственный руководитель / допускающий / производитель работ /
# наблюдающий / член бригады
MEMBER_ROLES = frozenset({
    "issuer", "supervisor", "admitter", "foreman", "observer", "member",
})

EVENT_TYPES = frozenset({
    "issued", "suspended", "resumed", "closed", "cancelled", "extended",
})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_ISSUED, STATUS_CANCELLED}),
    STATUS_ISSUED: frozenset({STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_SUSPENDED: frozenset({STATUS_ISSUED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_CLOSED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}


class WorkPermitTransitionError(ValueError):
    """Invalid work-permit status transition (maps to HTTP 409)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid work-permit transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise WorkPermitTransitionError unless current -> target is allowed."""
    if current not in WORK_PERMIT_STATUSES or target not in WORK_PERMIT_STATUSES:
        raise WorkPermitTransitionError(current, target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise WorkPermitTransitionError(current, target)


def is_work_type(value: str) -> bool:
    return value in WORK_TYPES


def is_member_role(value: str) -> bool:
    return value in MEMBER_ROLES
