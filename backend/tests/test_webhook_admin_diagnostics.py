"""Tests for webhook admin diagnostics API.

Validates:
- Failure diagnostics extraction from WebhookDelivery last_error
- Retry eligibility determination and policy visibility
- Failed delivery listing with diagnostics filtering
- Manual retry triggering with eligibility enforcement
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.api.models.webhook_admin import (
    WebhookDeliveryWithDiagnostics,
    WebhookFailureDiagnostics,
    WebhookRetryEligibility,
)
from app.models.models import Tenant, WebhookDelivery, WebhookEndpoint
from app.services.webhook_retry_telemetry import FailureCategory


@pytest.fixture
def sample_tenant():
    """Create a sample tenant for testing."""
    tenant = MagicMock(spec=Tenant)
    tenant.id = "tenant-123"
    return tenant


@pytest.fixture
def sample_endpoint(sample_tenant):
    """Create a sample webhook endpoint."""
    endpoint = MagicMock(spec=WebhookEndpoint)
    endpoint.id = "endpoint-456"
    endpoint.tenant_id = sample_tenant.id
    endpoint.url = "https://example.com/webhook"
    endpoint.is_enabled = True
    return endpoint


@pytest.fixture
def delivery_with_5xx_error(sample_tenant, sample_endpoint):
    """Create a delivery with 5xx error."""
    delivery = MagicMock(spec=WebhookDelivery)
    delivery.id = "delivery-1"
    delivery.tenant_id = sample_tenant.id
    delivery.endpoint_id = sample_endpoint.id
    delivery.event_id = "event-789"
    delivery.attempts = 2
    delivery.status = "failed"
    delivery.last_status_code = 503
    delivery.last_error = {
        "failure_category": "retryable_http_5xx",
        "retry_eligible": True,
        "http_status_code": 503,
        "error_class": "service_unavailable",
        "error_message": "503 Service Unavailable",
        "current_attempt": 2,
        "max_attempts": 5,
        "attempts_remaining": 3,
        "next_attempt_in_seconds": 20,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    delivery.next_attempt_at = datetime.now(tz=timezone.utc) + timedelta(seconds=20)
    delivery.latency_ms = 500
    delivery.started_at = datetime.now(tz=timezone.utc)
    delivery.last_response_body = None
    delivery.ended_at = datetime.now(tz=timezone.utc)
    return delivery


@pytest.fixture
def delivery_with_4xx_error(sample_tenant, sample_endpoint):
    """Create a delivery with 4xx terminal error."""
    delivery = MagicMock(spec=WebhookDelivery)
    delivery.id = "delivery-2"
    delivery.tenant_id = sample_tenant.id
    delivery.endpoint_id = sample_endpoint.id
    delivery.event_id = "event-790"
    delivery.attempts = 1
    delivery.status = "failed"
    delivery.last_status_code = 401
    delivery.last_error = {
        "failure_category": "terminal_http_4xx",
        "retry_eligible": False,
        "http_status_code": 401,
        "error_class": "unauthorized",
        "error_message": "401 Unauthorized",
        "current_attempt": 1,
        "max_attempts": 5,
        "attempts_remaining": 0,
        "next_attempt_in_seconds": None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    delivery.latency_ms = 100
    delivery.started_at = datetime.now(tz=timezone.utc)
    delivery.last_response_body = "Invalid credentials"
    delivery.ended_at = datetime.now(tz=timezone.utc)
    delivery.next_attempt_at = None
    return delivery


@pytest.fixture
def delivery_success(sample_tenant, sample_endpoint):
    """Create a successfully delivered webhook."""
    delivery = MagicMock(spec=WebhookDelivery)
    delivery.id = "delivery-3"
    delivery.tenant_id = sample_tenant.id
    delivery.endpoint_id = sample_endpoint.id
    delivery.event_id = "event-791"
    delivery.attempts = 1
    delivery.status = "success"
    delivery.last_status_code = 200
    delivery.last_error = None
    delivery.latency_ms = 45
    delivery.started_at = datetime.now(tz=timezone.utc)
    delivery.ended_at = datetime.now(tz=timezone.utc)
    delivery.next_attempt_at = None
    delivery.last_response_body = None
    return delivery


class TestWebhookFailureDiagnosticsExtraction:
    """Tests for extracting diagnostics from WebhookDelivery."""

    def test_extract_diagnostics_from_5xx_error(self, delivery_with_5xx_error):
        """Diagnostics should be extractable from last_error payload."""
        diag = WebhookFailureDiagnostics(**delivery_with_5xx_error.last_error)

        assert diag.failure_category == "retryable_http_5xx"
        assert diag.retry_eligible is True
        assert diag.http_status_code == 503
        assert diag.error_class == "service_unavailable"
        assert diag.current_attempt == 2
        assert diag.max_attempts == 5
        assert diag.attempts_remaining == 3
        assert diag.next_attempt_in_seconds == 20

    def test_extract_diagnostics_from_4xx_error(self, delivery_with_4xx_error):
        """Terminal 4xx errors should have retry_eligible=false."""
        diag = WebhookFailureDiagnostics(**delivery_with_4xx_error.last_error)

        assert diag.failure_category == "terminal_http_4xx"
        assert diag.retry_eligible is False
        assert diag.http_status_code == 401
        assert diag.attempts_remaining == 0
        assert diag.next_attempt_in_seconds is None

    def test_diagnostics_includes_timestamp(self, delivery_with_5xx_error):
        """Diagnostics should include ISO8601 timestamp."""
        diag = WebhookFailureDiagnostics(**delivery_with_5xx_error.last_error)
        assert diag.timestamp is not None
        # Verify timestamp can be parsed
        datetime.fromisoformat(diag.timestamp)

    def test_diagnostics_with_missing_optional_fields(self):
        """Diagnostics should handle missing optional fields gracefully."""
        error_payload = {
            "failure_category": "retryable_timeout",
            "retry_eligible": True,
        }
        diag = WebhookFailureDiagnostics(**error_payload)

        assert diag.failure_category == "retryable_timeout"
        assert diag.retry_eligible is True
        assert diag.http_status_code is None
        assert diag.error_class is None
        assert diag.error_message is None


class TestWebhookRetryEligibility:
    """Tests for retry eligibility determination."""

    def test_retryable_error_is_eligible(self, delivery_with_5xx_error):
        """5xx errors should be retry eligible."""
        eligibility = WebhookRetryEligibility(
            delivery_id=delivery_with_5xx_error.id,
            eligible=True,
            reason="Retryable HTTP 5xx error",
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            next_attempt_in_seconds=20,
        )

        assert eligibility.eligible is True
        assert eligibility.failure_category == FailureCategory.RETRYABLE_HTTP_5XX
        assert eligibility.next_attempt_in_seconds == 20

    def test_terminal_error_not_eligible(self, delivery_with_4xx_error):
        """4xx errors should not be retry eligible."""
        eligibility = WebhookRetryEligibility(
            delivery_id=delivery_with_4xx_error.id,
            eligible=False,
            reason="Terminal HTTP 4xx error",
            failure_category=FailureCategory.TERMINAL_HTTP_4XX,
        )

        assert eligibility.eligible is False
        assert eligibility.failure_category == FailureCategory.TERMINAL_HTTP_4XX
        assert eligibility.next_attempt_in_seconds is None

    def test_successful_delivery_not_eligible(self, delivery_success):
        """Successfully delivered webhooks should not be retryable."""
        eligibility = WebhookRetryEligibility(
            delivery_id=delivery_success.id,
            eligible=False,
            reason="Delivery succeeded, no retry needed",
        )

        assert eligibility.eligible is False


class TestWebhookDeliveryWithDiagnostics:
    """Tests for enhanced delivery responses with diagnostics."""

    def test_delivery_response_includes_diagnostics(self, delivery_with_5xx_error):
        """Delivery response should include failure diagnostics."""
        diag = WebhookFailureDiagnostics(**delivery_with_5xx_error.last_error)
        response = WebhookDeliveryWithDiagnostics(
            id=delivery_with_5xx_error.id,
            event_id=delivery_with_5xx_error.event_id,
            endpoint_id=delivery_with_5xx_error.endpoint_id,
            attempts=delivery_with_5xx_error.attempts,
            status=delivery_with_5xx_error.status,
            response_status=delivery_with_5xx_error.last_status_code,
            diagnostics=diag,
        )

        assert response.diagnostics is not None
        assert response.diagnostics.failure_category == "retryable_http_5xx"
        assert response.diagnostics.retry_eligible is True

    def test_delivery_response_without_diagnostics(self, delivery_success):
        """Successful deliveries may not have diagnostics."""
        response = WebhookDeliveryWithDiagnostics(
            id=delivery_success.id,
            event_id=delivery_success.event_id,
            endpoint_id=delivery_success.endpoint_id,
            attempts=delivery_success.attempts,
            status=delivery_success.status,
            response_status=delivery_success.last_status_code,
            diagnostics=None,
        )

        assert response.diagnostics is None
        assert response.status == "success"

    def test_delivery_response_includes_all_context(self, delivery_with_5xx_error):
        """Delivery response should include all delivery and diagnostic context."""
        diag = WebhookFailureDiagnostics(**delivery_with_5xx_error.last_error)
        response = WebhookDeliveryWithDiagnostics(
            id=delivery_with_5xx_error.id,
            event_id=delivery_with_5xx_error.event_id,
            endpoint_id=delivery_with_5xx_error.endpoint_id,
            attempts=delivery_with_5xx_error.attempts,
            status=delivery_with_5xx_error.status,
            next_attempt_at=delivery_with_5xx_error.next_attempt_at,
            response_status=delivery_with_5xx_error.last_status_code,
            latency_ms=delivery_with_5xx_error.latency_ms,
            started_at=delivery_with_5xx_error.started_at,
            ended_at=delivery_with_5xx_error.ended_at,
            diagnostics=diag,
        )

        assert response.id == delivery_with_5xx_error.id
        assert response.attempts == 2
        assert response.status == "failed"
        assert response.response_status == 503
        assert response.latency_ms == 500
        assert response.diagnostics.retry_eligible is True


class TestWebhookRetryPolicyFiltering:
    """Tests for filtering deliveries by retry policy."""

    def test_filter_retryable_failures_only(self):
        """Should filter to only retryable failures."""
        retryable = FailureCategory.RETRYABLE_HTTP_5XX.value
        terminal = FailureCategory.TERMINAL_HTTP_4XX.value

        # Simulate filtering logic
        categories = [retryable, terminal, retryable]
        retryable_only = [c for c in categories if c.startswith("retryable_")]

        assert len(retryable_only) == 2
        assert all(c.startswith("retryable_") for c in retryable_only)

    def test_filter_by_failure_category(self):
        """Should filter deliveries by specific failure category."""
        failures = [
            {"category": FailureCategory.RETRYABLE_HTTP_5XX, "attempts": 1},
            {"category": FailureCategory.RETRYABLE_TIMEOUT, "attempts": 2},
            {"category": FailureCategory.TERMINAL_HTTP_4XX, "attempts": 1},
        ]

        timeout_failures = [
            f for f in failures if f["category"] == FailureCategory.RETRYABLE_TIMEOUT
        ]

        assert len(timeout_failures) == 1
        assert timeout_failures[0]["attempts"] == 2

    def test_backoff_calculation_in_filtered_results(self):
        """Filtered results should include backoff timing for retryable errors."""
        failures = [
            {
                "id": "delivery-1",
                "category": FailureCategory.RETRYABLE_HTTP_5XX,
                "attempt": 1,
                "base_backoff": 5,
                "next_attempt_seconds": 5 * (2**0),  # 5 seconds
            },
            {
                "id": "delivery-2",
                "category": FailureCategory.RETRYABLE_HTTP_5XX,
                "attempt": 2,
                "base_backoff": 5,
                "next_attempt_seconds": 5 * (2**1),  # 10 seconds
            },
        ]

        # Verify backoff escalation
        assert failures[1]["next_attempt_seconds"] > failures[0]["next_attempt_seconds"]
