"""Deprecated compat-shim — training ops moved to :mod:`app.modules.training.operations`
(ARCH-1).

Kept as a re-export so ``from app.domains.training.service import …`` keeps working until the
next major (POST-1 removes the ``domains/*`` shims). New code should import from
``app.modules.training``.
"""

from __future__ import annotations

from app.modules.training.operations import (  # noqa: F401  (compat re-export)
    TrainingCertificateIssueResult,
    assign_training_plan,
    issue_certificate,
    register_training_session,
    upcoming_certificate_expirations,
)
