"""Progressive compatibility layer for approval/sign/EDO ORM models.

This module is part of the staged decomposition of ``app.models.models``.
It re-exports workflow-related entities so new code can stop depending on the
mega-module while table declarations remain stable.
"""

from app.models.models import (
    ApprovalDecision,
    ApprovalDecisionType,
    ApprovalInstance,
    ApprovalInstanceStep,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRoute,
    ApprovalRouteStep,
    EdoDirection,
    EdoMessage,
    EdoReceipt,
    EdoStatus,
    EdoStatusEvent,
    EdoStatusHistory,
    EdoWebhookInbox,
    Signature,
    SignatureStatus,
    SignatureType,
    SignatureRequest,
)

__all__ = [
    "ApprovalDecision",
    "ApprovalDecisionType",
    "ApprovalInstance",
    "ApprovalInstanceStep",
    "ApprovalRequest",
    "ApprovalRequestStatus",
    "ApprovalRoute",
    "ApprovalRouteStep",
    "EdoDirection",
    "EdoMessage",
    "EdoReceipt",
    "EdoStatus",
    "EdoStatusEvent",
    "EdoStatusHistory",
    "EdoWebhookInbox",
    "Signature",
    "SignatureRequest",
    "SignatureStatus",
    "SignatureType",
]
