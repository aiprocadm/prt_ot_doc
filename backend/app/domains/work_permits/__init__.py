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
from app.domains.work_permits.service import (
    add_member, cancel, close, create_admission, create_briefing, create_work_permit, delete_draft,
    extend, get_admission, get_briefing, issue, list_admissions, list_briefings, list_events,
    list_members, remove_member, resume, suspend, update_admission, update_briefing,
    update_work_permit,
)

__all__ = [
    "ALLOWED_TRANSITIONS", "EVENT_TYPES", "MEMBER_ROLES",
    "STATUS_CANCELLED", "STATUS_CLOSED", "STATUS_DRAFT", "STATUS_ISSUED", "STATUS_SUSPENDED",
    "WORK_PERMIT_STATUSES", "WORK_TYPES", "WorkPermitTransitionError",
    "is_member_role", "is_work_type", "validate_transition",
    "add_member", "cancel", "close", "create_admission", "create_briefing", "create_work_permit",
    "delete_draft", "extend", "get_admission", "get_briefing", "issue", "list_admissions",
    "list_briefings", "list_events", "list_members", "remove_member", "resume", "suspend",
    "update_admission", "update_briefing", "update_work_permit",
]
