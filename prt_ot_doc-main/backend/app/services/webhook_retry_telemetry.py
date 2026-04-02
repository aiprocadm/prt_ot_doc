"""Webhook and outbox retry telemetry classification and diagnostics.

Provides structured failure classification, retry policy analysis, and diagnostic
telemetry for webhook delivery and outbox processing. Enables operators to analyze
retry patterns and diagnose delivery failures with runbook-ready context.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

__all__ = [
    "FailureCategory",
    "RetryPolicy",
    "RetryTelemetry",
    "classify_failure",
    "calculate_retry_info",
    "create_failure_diagnostics",
]


class FailureCategory(str, enum.Enum):
    """Categorizes webhook/outbox delivery failures for retry eligibility."""

    # Retryable: server-side or network transient issues
    RETRYABLE_HTTP_5XX = "retryable_http_5xx"  # 500, 502, 503, 504
    RETRYABLE_TIMEOUT = "retryable_timeout"  # Connection or read timeout
    RETRYABLE_RATE_LIMIT = "retryable_rate_limit"  # 429 Too Many Requests
    RETRYABLE_THROTTLE = "retryable_throttle"  # 408 Request Timeout
    RETRYABLE_CONNECTION = "retryable_connection"  # DNS, connection refused, etc.

    # Terminal: client-side or permanent errors (no retry)
    TERMINAL_HTTP_4XX = "terminal_http_4xx"  # 400, 401, 403, 404, etc. (except 408/429)
    TERMINAL_MAX_ATTEMPTS = "terminal_max_attempts"  # Exceeded max retry limit
    TERMINAL_VALIDATION = "terminal_validation"  # Invalid request structure
    TERMINAL_AUTH = "terminal_auth"  # Authentication/authorization failure

    # Special cases
    UNKNOWN = "unknown"  # Unable to classify
    INTERNAL_ERROR = "internal_error"  # Processing error on our side


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry eligibility and backoff calculation policy."""

    eligible: bool
    """True if this failure should trigger a retry attempt."""

    category: FailureCategory
    """Specific failure category for diagnostics."""

    backoff_seconds: int | None
    """Seconds to wait before next attempt; None if no retry."""

    max_attempts: int
    """Maximum retry attempts allowed."""

    attempt_number: int
    """Current attempt number (1-based)."""

    previous_attempts: int
    """Adjustment for tracking actual attempts (0 for first, 1 for retries)."""


@dataclass(frozen=True, slots=True)
class RetryTelemetry:
    """Complete telemetry for a retry attempt."""

    failure_category: FailureCategory
    retry_eligible: bool
    next_attempt_in_seconds: int | None
    current_attempt: int
    max_attempts: int
    attempts_remaining: int
    http_status_code: int | None
    error_class: str | None
    error_message: str | None
    timestamp: str  # ISO8601 UTC


def classify_failure(
    *,
    status_code: int | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> FailureCategory:
    """Classify a webhook/outbox delivery failure.

    Args:
        status_code: HTTP status code if applicable.
        error_class: Error classification (timeout, connection, etc.).
        error_message: Human-readable error message.

    Returns:
        FailureCategory indicating retry eligibility.
    """
    if error_class == "timeout":
        return FailureCategory.RETRYABLE_TIMEOUT
    if error_class == "connection":
        return FailureCategory.RETRYABLE_CONNECTION

    if status_code is not None:
        if status_code >= 500:
            return FailureCategory.RETRYABLE_HTTP_5XX
        if status_code == 429:
            return FailureCategory.RETRYABLE_RATE_LIMIT
        if status_code == 408:
            return FailureCategory.RETRYABLE_THROTTLE
        if status_code >= 400:
            return FailureCategory.TERMINAL_HTTP_4XX

    if error_class == "max_attempts_exceeded":
        return FailureCategory.TERMINAL_MAX_ATTEMPTS
    if error_class == "validation":
        return FailureCategory.TERMINAL_VALIDATION

    if not error_class and not status_code:
        return FailureCategory.UNKNOWN

    return FailureCategory.UNKNOWN


def calculate_retry_info(
    *,
    failure_category: FailureCategory,
    current_attempt: int,
    max_attempts: int,
    backoff_seconds_base: int,  # Base backoff (e.g., 5)
    backoff_seconds_max: int,  # Max backoff cap (e.g., 300)
) -> RetryPolicy:
    """Calculate retry policy for a failure.

    Args:
        failure_category: Failure categorization result.
        current_attempt: 1-based attempt number.
        max_attempts: Maximum retry limit.
        backoff_seconds_base: Base exponential backoff value.
        backoff_seconds_max: Maximum backoff cap.

    Returns:
        RetryPolicy with eligibility and backoff calculation.
    """
    retryable = failure_category.value.startswith("retryable_")
    exceeded = current_attempt >= max_attempts

    if not retryable or exceeded:
        return RetryPolicy(
            eligible=False,
            category=failure_category,
            backoff_seconds=None,
            max_attempts=max_attempts,
            attempt_number=current_attempt,
            previous_attempts=current_attempt - 1,
        )

    # Calculate exponential backoff with cap
    exponent = max(current_attempt - 1, 0)
    backoff = min(backoff_seconds_base * (2**exponent), backoff_seconds_max)

    return RetryPolicy(
        eligible=True,
        category=failure_category,
        backoff_seconds=int(backoff),
        max_attempts=max_attempts,
        attempt_number=current_attempt,
        previous_attempts=current_attempt - 1,
    )


def create_failure_diagnostics(
    *,
    failure_category: FailureCategory,
    retry_policy: RetryPolicy,
    http_status_code: int | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    """Create structured failure diagnostics for logging/storage.

    Args:
        failure_category: Failure categorization.
        retry_policy: Calculated retry policy.
        http_status_code: HTTP status code if applicable.
        error_class: Error class for routing.
        error_message: Human-readable error.

    Returns:
        Dictionary with complete diagnostic context.
    """
    return {
        "failure_category": failure_category.value,
        "retry_eligible": retry_policy.eligible,
        "next_attempt_in_seconds": retry_policy.backoff_seconds,
        "current_attempt": retry_policy.attempt_number,
        "max_attempts": retry_policy.max_attempts,
        "attempts_remaining": max(0, retry_policy.max_attempts - retry_policy.attempt_number),
        "http_status_code": http_status_code,
        "error_class": error_class,
        "error_message": error_message,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


def create_retry_telemetry(
    *,
    failure_category: FailureCategory,
    retry_policy: RetryPolicy,
    http_status_code: int | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
) -> RetryTelemetry:
    """Create typed retry telemetry for structured logging.

    Args:
        failure_category: Failure categorization.
        retry_policy: Calculated retry policy.
        http_status_code: HTTP status code if applicable.
        error_class: Error class for routing.
        error_message: Human-readable error.

    Returns:
        RetryTelemetry with complete context.
    """
    return RetryTelemetry(
        failure_category=failure_category,
        retry_eligible=retry_policy.eligible,
        next_attempt_in_seconds=retry_policy.backoff_seconds,
        current_attempt=retry_policy.attempt_number,
        max_attempts=retry_policy.max_attempts,
        attempts_remaining=max(0, retry_policy.max_attempts - retry_policy.attempt_number),
        http_status_code=http_status_code,
        error_class=error_class,
        error_message=error_message,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
