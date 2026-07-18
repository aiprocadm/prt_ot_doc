"""Admin diagnostics models for webhook delivery management.

Provides structured responses for webhook delivery failure analysis and retry policy visibility.
Enables operators to understand failure reasons and retry eligibility through admin APIs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.services.webhook_retry_telemetry import FailureCategory


class WebhookFailureDiagnostics(BaseModel):
    """Complete failure diagnostics with retry policy information."""

    failure_category: FailureCategory | str
    """Category of failure for classification and runbook routing."""

    retry_eligible: bool
    """Whether this failure can be retried (true) or is terminal (false)."""

    http_status_code: int | None = None
    """HTTP status code if available."""

    error_class: str | None = None
    """Error class for technical routing."""

    error_message: str | None = None
    """Human-readable error description."""

    current_attempt: int = 1
    """Current attempt number (1-based)."""

    max_attempts: int = 5
    """Maximum retry attempts allowed."""

    attempts_remaining: int = 4
    """Remaining attempts before giving up."""

    next_attempt_in_seconds: int | None = None
    """Seconds to wait before next retry; None if not retryable."""

    timestamp: str | None = None
    """ISO8601 timestamp when failure was recorded."""


class WebhookDeliveryWithDiagnostics(BaseModel):
    """Enhanced webhook delivery response with diagnostics."""

    id: str
    event_id: str
    endpoint_id: str
    attempts: int
    status: str  # success, failed, pending
    next_attempt_at: datetime | None = None
    response_status: int | None = None
    last_response_body: str | None = None
    latency_ms: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    # New diagnostic fields
    diagnostics: WebhookFailureDiagnostics | None = Field(default=None)
    """Failure diagnostics if status is 'failed' or 'pending'."""


class WebhookRetryEligibility(BaseModel):
    """Simple retry eligibility check response."""

    delivery_id: str
    eligible: bool
    """True if delivery can be retried."""

    reason: str
    """Human-readable reason (e.g., 'Server error, retryable', 'Invalid request, terminal')."""

    failure_category: FailureCategory | str | None = None
    """Failure category if applicable."""

    next_attempt_in_seconds: int | None = None
    """Seconds to wait before allowing retry."""


class WebhookRetryRequest(BaseModel):
    """Request to manually trigger webhook retry."""

    delivery_id: str
    reason: str | None = Field(default=None)
    """Optional reason for manual retry trigger."""


class WebhookRetryResponse(BaseModel):
    """Response after triggering manual retry."""

    delivery_id: str
    status: str
    """Status after retry trigger (e.g., 'queued', 'failed')."""

    next_attempt_at: datetime | None = None
    message: str | None = None
    """Human-readable outcome message."""


class WebhookDeliveryFilter(BaseModel):
    """Filter criteria for delivery listing."""

    status: str | None = Field(default=None)
    """Filter by delivery status (success, failed, pending)."""

    failure_category: str | None = Field(default=None)
    """Filter by failure category (retryable_*, terminal_*, unknown)."""

    retry_eligible_only: bool = Field(default=False)
    """If true, only return failures that are retryable."""

    endpoint_id: str | None = Field(default=None)
    """Filter by endpoint ID."""

    event_type: str | None = Field(default=None)
    """Filter by event type."""

    limit: int = Field(default=100, le=1000)
    """Maximum results to return."""
