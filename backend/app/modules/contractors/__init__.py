"""Contractors bounded context (canonical home — ARCH-1).

Public surface: ORM models (``.models``), pure document-expiry classification
(``.documents``) and the admission-readiness engine (``.lifecycle``). The legacy
``app.domains.contractors`` compat-shim was removed in POST-1 (2026-07-02).
"""

from __future__ import annotations

from app.modules.contractors.documents import (  # noqa: F401  (public re-export)
    best_document,
    document_expiry_status,
    requirement_status,
)
from app.modules.contractors.lifecycle import (  # noqa: F401  (public re-export)
    TRAINING_INTERVAL_DAYS,
    DocumentRequirement,
    EmployeeVerdict,
    ReadinessStatus,
    evaluate_employee,
)

__all__ = [
    "best_document",
    "document_expiry_status",
    "requirement_status",
    "TRAINING_INTERVAL_DAYS",
    "DocumentRequirement",
    "EmployeeVerdict",
    "ReadinessStatus",
    "evaluate_employee",
]
