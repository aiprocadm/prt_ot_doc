"""Deprecated compat-shim — canonical location is :mod:`app.modules.training` (ARCH-1)."""

from app.modules.training.operations import (  # noqa: F401  (compat re-export)
    TrainingCertificateIssueResult,
    assign_training_plan,
    issue_certificate,
    register_training_session,
    upcoming_certificate_expirations,
)

__all__ = [
    "assign_training_plan",
    "issue_certificate",
    "register_training_session",
    "TrainingCertificateIssueResult",
    "upcoming_certificate_expirations",
]
