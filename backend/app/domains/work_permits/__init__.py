"""Domain logic for work permits (наряды-допуски)."""

from app.domains.work_permits.lifecycle import (
    ALLOWED_TRANSITIONS,
    EVENT_TYPES,
    MEMBER_ROLES,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_ISSUED,
    STATUS_SUSPENDED,
    WORK_PERMIT_STATUSES,
    WORK_TYPES,
    WorkPermitTransitionError,
    is_member_role,
    is_work_type,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS", "EVENT_TYPES", "MEMBER_ROLES",
    "STATUS_CANCELLED", "STATUS_CLOSED", "STATUS_DRAFT", "STATUS_ISSUED", "STATUS_SUSPENDED",
    "WORK_PERMIT_STATUSES", "WORK_TYPES", "WorkPermitTransitionError",
    "is_member_role", "is_work_type", "validate_transition",
]
