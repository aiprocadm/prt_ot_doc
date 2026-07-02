"""PPE bounded context (canonical home — ARCH-1).

Public surface: the pure requirement/card algorithm services (``.services``), the
DB-backed issuance/card/journal operations (``.operations``) and the pure issue-FSM
+ card-line rules (``.lifecycle``). The legacy ``app.domains.ppe`` compat-shim
was removed in POST-1 (2026-07-02).
"""

from app.modules.ppe.operations import (  # noqa: F401  (public re-export)
    build_journal_export,
    build_personal_card_766n,
    build_personal_card_payload,
    issue_ppe_item,
    list_expiring_issues,
    replace_issue,
    return_issue,
    writeoff_issue,
)
from app.modules.ppe.services import (  # noqa: F401  (public re-export)
    PPEIssueEvent,
    PPENormService,
    PPEPersonalCardService,
    RiskPPEProjectionService,
)

__all__ = [
    "PPEIssueEvent",
    "PPEPersonalCardService",
    "PPENormService",
    "RiskPPEProjectionService",
    "build_personal_card_766n",
    "build_personal_card_payload",
    "build_journal_export",
    "issue_ppe_item",
    "list_expiring_issues",
    "replace_issue",
    "return_issue",
    "writeoff_issue",
]
