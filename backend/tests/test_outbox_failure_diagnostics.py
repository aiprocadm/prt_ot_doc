"""Tests for webhook/outbox failure diagnostics integration.

Validates that OutboxProcessor properly integrates failure classification
and creates structured retry telemetry in error payloads.
"""

from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.models.models import OutboxStatus
from app.services.outbox import DispatchResult, OutboxProcessor


@pytest.fixture
def mock_settings():
    """Create mock settings for OutboxProcessor."""
    settings = MagicMock(spec=Settings)
    settings.outbox_in_progress_timeout_seconds = 900
    settings.outbox_max_attempts = 5
    settings.outbox_retry_backoff_seconds = 5
    settings.outbox_retry_backoff_max_seconds = 300
    return settings


@pytest.fixture
def processor(mock_settings):
    """Create OutboxProcessor with mock session and settings."""
    mock_session = MagicMock()
    processor = OutboxProcessor(mock_session)
    processor.settings = mock_settings
    return processor


class TestOutboxProcessorFailureDiagnostics:
    """Tests for OutboxProcessor error payload generation."""

    def test_error_payload_for_http_5xx(self, processor):
        """Error payload for 5xx should include retry_eligible=true."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="service_unavailable",
            error_message="503 Service Unavailable",
            status_code=503,
        )

        payload = processor._error_payload(result, attempt_number=1)

        assert payload is not None
        assert payload["failure_category"] == "retryable_http_5xx"
        assert payload["retry_eligible"] is True
        assert payload["http_status_code"] == 503
        assert payload["error_class"] == "service_unavailable"
        assert payload["current_attempt"] == 1
        assert payload["max_attempts"] == 5
        assert "next_attempt_in_seconds" in payload
        assert "timestamp" in payload

    def test_error_payload_for_http_4xx(self, processor):
        """Error payload for 4xx should include retry_eligible=false."""
        result = DispatchResult(
            status=OutboxStatus.DEAD,
            error_class="not_found",
            error_message="404 Not Found",
            status_code=404,
        )

        payload = processor._error_payload(result, attempt_number=1)

        assert payload is not None
        assert payload["failure_category"] == "terminal_http_4xx"
        assert payload["retry_eligible"] is False
        assert payload["http_status_code"] == 404
        assert payload["error_class"] == "not_found"
        assert payload["next_attempt_in_seconds"] is None

    def test_error_payload_for_timeout(self, processor):
        """Error payload for timeout should include retry_eligible=true."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="timeout",
            error_message="Request timeout after 30s",
            status_code=None,
        )

        payload = processor._error_payload(result, attempt_number=1)

        assert payload is not None
        assert payload["failure_category"] == "retryable_timeout"
        assert payload["retry_eligible"] is True
        assert payload["error_class"] == "timeout"
        assert "next_attempt_in_seconds" in payload

    def test_error_payload_escalating_backoff(self, processor):
        """Error payload should reflect escalating backoff on later attempts."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="service_unavailable",
            error_message="503 Service Unavailable",
            status_code=503,
        )

        payload_attempt_1 = processor._error_payload(result, attempt_number=1)
        payload_attempt_3 = processor._error_payload(result, attempt_number=3)

        assert payload_attempt_1["next_attempt_in_seconds"] is not None
        assert payload_attempt_3["next_attempt_in_seconds"] is not None
        # Attempt 3 should have longer or equal backoff than attempt 1
        # (exponential: 2^0 * 5 vs 2^2 * 5 = 5 vs 20)
        assert (
            payload_attempt_3["next_attempt_in_seconds"]
            >= payload_attempt_1["next_attempt_in_seconds"]
        )

    def test_error_payload_at_max_attempts(self, processor):
        """Error payload at max attempts should not be retryable."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="service_unavailable",
            error_message="503 Service Unavailable",
            status_code=503,
        )

        payload = processor._error_payload(result, attempt_number=5)  # At max

        assert payload is not None
        assert payload["current_attempt"] == 5
        assert payload["attempts_remaining"] == 0
        # Even though it's a retryable error, we're at max attempts
        assert payload["retry_eligible"] is False

    def test_error_payload_respects_max_backoff_cap(self, processor):
        """Error payload backoff should not exceed max cap."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="service_unavailable",
            error_message="503 Service Unavailable",
            status_code=503,
        )

        # Attempt 4 with exponential backoff would calculate 2^3 * 5 = 40, capped at 300
        payload = processor._error_payload(result, attempt_number=4)

        assert payload["next_attempt_in_seconds"] is not None
        assert payload["next_attempt_in_seconds"] >= 40 * 0.9  # Account for jitter
        assert payload["next_attempt_in_seconds"] <= 300

    def test_error_payload_includes_all_context(self, processor):
        """Error payload should include complete diagnostic context."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="rate_limited",
            error_message="429 Too Many Requests",
            status_code=429,
        )

        payload = processor._error_payload(result, attempt_number=2)

        # Verify all required fields are present
        assert "failure_category" in payload
        assert "retry_eligible" in payload
        assert "next_attempt_in_seconds" in payload
        assert "current_attempt" in payload
        assert "max_attempts" in payload
        assert "attempts_remaining" in payload
        assert "http_status_code" in payload
        assert "error_class" in payload
        assert "error_message" in payload
        assert "timestamp" in payload

    def test_error_payload_for_connection_error(self, processor):
        """Error payload for connection errors should be retryable."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="connection",
            error_message="Connection refused: 127.0.0.1:9999",
            status_code=None,
        )

        payload = processor._error_payload(result, attempt_number=1)

        assert payload is not None
        assert payload["failure_category"] == "retryable_connection"
        assert payload["retry_eligible"] is True
        assert payload["error_class"] == "connection"

    def test_error_payload_http_429_rate_limit(self, processor):
        """Error payload for 429 should be classified as rate limit."""
        result = DispatchResult(
            status=OutboxStatus.FAILED,
            error_class="rate_limit",
            error_message="429 Too Many Requests",
            status_code=429,
        )

        payload = processor._error_payload(result, attempt_number=1)

        assert payload is not None
        assert payload["failure_category"] == "retryable_rate_limit"
        assert payload["retry_eligible"] is True
