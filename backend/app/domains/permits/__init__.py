"""Domain logic for personal permits (личные допуски)."""

from app.domains.permits.lifecycle import (
    ALLOWED_TRANSITIONS,
    PERMIT_STATUS_ACTIVE,
    PERMIT_STATUS_EXPIRED,
    PERMIT_STATUS_REVOKED,
    PERMIT_STATUSES,
    PermitTransitionError,
    due_status,
    is_expired,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "PERMIT_STATUS_ACTIVE",
    "PERMIT_STATUS_EXPIRED",
    "PERMIT_STATUS_REVOKED",
    "PERMIT_STATUSES",
    "PermitTransitionError",
    "due_status",
    "is_expired",
    "validate_transition",
]
