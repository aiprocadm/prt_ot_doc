"""Deprecated compat-shim — canonical location is :mod:`app.modules.ppe.operations` (ARCH-1)."""

from __future__ import annotations

from app.modules.ppe.operations import (  # noqa: F401  (compat re-export)
    build_journal_export,
    build_personal_card_766n,
    build_personal_card_payload,
    issue_ppe_item,
    list_expiring_issues,
    replace_issue,
    return_issue,
    writeoff_issue,
)

__all__ = [
    "build_personal_card_766n",
    "build_personal_card_payload",
    "build_journal_export",
    "issue_ppe_item",
    "list_expiring_issues",
    "replace_issue",
    "return_issue",
    "writeoff_issue",
]
