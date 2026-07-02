"""Deprecated compat-shim — canonical location is :mod:`app.modules.ppe.lifecycle` (ARCH-1)."""

from __future__ import annotations

from app.modules.ppe.lifecycle import (  # noqa: F401  (compat re-export)
    ADMISSION_BLOCKING_STATUSES,
    ALLOWED_TRANSITIONS,
    ISSUE_STATUS_ISSUED,
    ISSUE_STATUS_LOST,
    ISSUE_STATUS_REPLACED,
    ISSUE_STATUS_RETURNED,
    ISSUE_STATUS_WRITTEN_OFF,
    ISSUE_STATUSES,
    TERMINAL_STATUSES,
    IssueView,
    PPETransitionError,
    card_line_status,
    fold_card_status,
    match_issues_for_norm_line,
    norm_line_key,
    validate_transition,
)

__all__ = [
    "ADMISSION_BLOCKING_STATUSES",
    "ALLOWED_TRANSITIONS",
    "ISSUE_STATUS_ISSUED",
    "ISSUE_STATUS_LOST",
    "ISSUE_STATUS_REPLACED",
    "ISSUE_STATUS_RETURNED",
    "ISSUE_STATUS_WRITTEN_OFF",
    "ISSUE_STATUSES",
    "TERMINAL_STATUSES",
    "IssueView",
    "PPETransitionError",
    "card_line_status",
    "fold_card_status",
    "match_issues_for_norm_line",
    "norm_line_key",
    "validate_transition",
]
