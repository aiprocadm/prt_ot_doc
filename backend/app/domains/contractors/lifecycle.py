"""Deprecated compat-shim — canonical location is :mod:`app.modules.contractors.lifecycle` (ARCH-1)."""

from __future__ import annotations

from app.modules.contractors.lifecycle import (  # noqa: F401  (compat re-export)
    TRAINING_INTERVAL_DAYS,
    DocumentRequirement,
    EmployeeVerdict,
    ReadinessStatus,
    evaluate_employee,
)

__all__ = [
    "TRAINING_INTERVAL_DAYS",
    "DocumentRequirement",
    "EmployeeVerdict",
    "ReadinessStatus",
    "evaluate_employee",
]
