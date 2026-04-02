"""Progressive compatibility layer for approval/signing v1 ORM models.

This module is part of the staged decomposition of ``app.models.models``.
It re-exports the approval/signing entities used by the legacy v1 routes so
new code can move away from the mega-module without changing table mappings.
"""

from app.models.models import (
    ApprovalDecisionLog,
    ApprovalProcess,
    ApprovalProcessStatus,
    ApprovalRoute,
    ApprovalTask,
    ApprovalTaskStatus,
    EdoEnvelope,
    EdoEnvelopeStatus,
    SignatureRequest,
    SignatureRequestStatus,
    WebhookEndpoint,
)

__all__ = [
    "ApprovalDecisionLog",
    "ApprovalProcess",
    "ApprovalProcessStatus",
    "ApprovalRoute",
    "ApprovalTask",
    "ApprovalTaskStatus",
    "EdoEnvelope",
    "EdoEnvelopeStatus",
    "SignatureRequest",
    "SignatureRequestStatus",
    "WebhookEndpoint",
]
