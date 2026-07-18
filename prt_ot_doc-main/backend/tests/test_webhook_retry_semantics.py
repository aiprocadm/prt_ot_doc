"""Tests for webhook retry semantics and failure classification.

Validates:
- Failure classification across HTTP status codes and error types
- Retry policy calculation for retryable vs terminal failures
- Structured diagnostics in outbox error payloads
- Retry telemetry contract in webhook delivery lifecycle
"""

from datetime import datetime

from app.services.webhook_retry_telemetry import (
    FailureCategory,
    calculate_retry_info,
    classify_failure,
    create_failure_diagnostics,
)


class TestFailureClassification:
    """Tests for failure_category classification logic."""

    def test_classify_http_5xx_as_retryable(self):
        """HTTP 5xx errors should be classified as retryable."""
        for code in [500, 502, 503, 504]:
            result = classify_failure(status_code=code)
            assert result == FailureCategory.RETRYABLE_HTTP_5XX

    def test_classify_http_429_as_retryable_rate_limit(self):
        """HTTP 429 (Too Many Requests) should be retryable."""
        result = classify_failure(status_code=429)
        assert result == FailureCategory.RETRYABLE_RATE_LIMIT

    def test_classify_http_408_as_retryable_throttle(self):
        """HTTP 408 (Request Timeout) should be retryable."""
        result = classify_failure(status_code=408)
        assert result == FailureCategory.RETRYABLE_THROTTLE

    def test_classify_http_4xx_as_terminal(self):
        """HTTP 4xx (except 408/429) should be terminal."""
        for code in [400, 401, 403, 404, 405, 410]:
            result = classify_failure(status_code=code)
            assert result == FailureCategory.TERMINAL_HTTP_4XX

    def test_classify_timeout_error_as_retryable(self):
        """Timeout errors should be retryable."""
        result = classify_failure(error_class="timeout")
        assert result == FailureCategory.RETRYABLE_TIMEOUT

    def test_classify_connection_error_as_retryable(self):
        """Connection errors should be retryable."""
        result = classify_failure(error_class="connection")
        assert result == FailureCategory.RETRYABLE_CONNECTION

    def test_classify_max_attempts_as_terminal(self):
        """Max attempts exceeded should be terminal."""
        result = classify_failure(error_class="max_attempts_exceeded")
        assert result == FailureCategory.TERMINAL_MAX_ATTEMPTS

    def test_classify_unknown_error_as_unknown(self):
        """Unknown errors with no context should be unknown."""
        result = classify_failure()
        assert result == FailureCategory.UNKNOWN

    def test_classify_prioritizes_status_code(self):
        """Status code should take precedence over generic error_class."""
        result = classify_failure(status_code=500, error_class="generic_error")
        assert result == FailureCategory.RETRYABLE_HTTP_5XX


class TestRetryPolicyCalculation:
    """Tests for retry_policy calculation and backoff."""

    def test_retryable_failure_eligible_for_retry(self):
        """Retryable failures should be marked as retry_eligible=true."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            current_attempt=1,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is True
        assert policy.category == FailureCategory.RETRYABLE_HTTP_5XX

    def test_terminal_failure_not_eligible_for_retry(self):
        """Terminal failures should be marked as retry_eligible=false."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.TERMINAL_HTTP_4XX,
            current_attempt=1,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is False
        assert policy.backoff_seconds is None

    def test_max_attempts_exceeded_not_eligible(self):
        """Reaching max_attempts should prevent retry even for retryable errors."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            current_attempt=5,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is False
        assert policy.backoff_seconds is None

    def test_exponential_backoff_calculation(self):
        """Backoff should follow exponential pattern: base * 2^(attempt-1)."""
        test_cases = [
            (1, 5),  # 5 * 2^0 = 5
            (2, 10),  # 5 * 2^1 = 10
            (3, 20),  # 5 * 2^2 = 20
            (4, 40),  # 5 * 2^3 = 40
        ]
        for attempt, expected_base_backoff in test_cases:
            policy = calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=attempt,
                max_attempts=10,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            )
            assert policy.backoff_seconds is not None
            # Allow for jitter variance (±10% for test stability)
            assert expected_base_backoff * 0.9 <= policy.backoff_seconds <= expected_base_backoff * 1.1

    def test_backoff_respects_max_cap(self):
        """Backoff should never exceed backoff_seconds_max."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            current_attempt=20,  # Would be 5 * 2^19 without cap
            max_attempts=25,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.backoff_seconds is not None
        assert policy.backoff_seconds <= 300

    def test_attempt_number_tracking(self):
        """Policy should track attempt numbers accurately."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            current_attempt=3,
            max_attempts=7,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.attempt_number == 3
        assert policy.max_attempts == 7
        assert policy.previous_attempts == 2  # current - 1


class TestFailureDiagnostics:
    """Tests for structured failure diagnostics."""

    def test_diagnostics_include_failure_category(self):
        """Diagnostics should include failure_category."""
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=1,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert diag["failure_category"] == "retryable_http_5xx"

    def test_diagnostics_include_retry_eligibility(self):
        """Diagnostics should include retry_eligible flag."""
        diag_retryable = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=1,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert diag_retryable["retry_eligible"] is True

        diag_terminal = create_failure_diagnostics(
            failure_category=FailureCategory.TERMINAL_HTTP_4XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.TERMINAL_HTTP_4XX,
                current_attempt=1,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert diag_terminal["retry_eligible"] is False

    def test_diagnostics_include_next_attempt_timing(self):
        """Diagnostics should include next_attempt_in_seconds."""
        policy = calculate_retry_info(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            current_attempt=2,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=policy,
        )
        assert diag["next_attempt_in_seconds"] is not None
        assert diag["next_attempt_in_seconds"] > 0

    def test_diagnostics_include_attempt_counters(self):
        """Diagnostics should include attempt count tracking."""
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=2,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert diag["current_attempt"] == 2
        assert diag["max_attempts"] == 5
        assert diag["attempts_remaining"] == 3

    def test_diagnostics_include_error_context(self):
        """Diagnostics should include HTTP status and error details."""
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=1,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
            http_status_code=502,
            error_class="bad_gateway",
            error_message="502 Bad Gateway from upstream",
        )
        assert diag["http_status_code"] == 502
        assert diag["error_class"] == "bad_gateway"
        assert diag["error_message"] == "502 Bad Gateway from upstream"

    def test_diagnostics_include_timestamp(self):
        """Diagnostics should include ISO8601 timestamp."""
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=1,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert "timestamp" in diag
        assert diag["timestamp"]
        # Verify it's a valid ISO8601 string
        datetime.fromisoformat(diag["timestamp"])

    def test_diagnostics_attempts_remaining_zero_at_max(self):
        """Attempts remaining should be 0 when at max attempts."""
        diag = create_failure_diagnostics(
            failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
            retry_policy=calculate_retry_info(
                failure_category=FailureCategory.RETRYABLE_HTTP_5XX,
                current_attempt=5,
                max_attempts=5,
                backoff_seconds_base=5,
                backoff_seconds_max=300,
            ),
        )
        assert diag["attempts_remaining"] == 0


class TestFailureClassificationScenarios:
    """Integration tests for realistic failure scenarios."""

    def test_scenario_transient_network_error(self):
        """Transient network errors should be retryable with backoff."""
        category = classify_failure(error_class="connection")
        assert category == FailureCategory.RETRYABLE_CONNECTION

        policy = calculate_retry_info(
            failure_category=category,
            current_attempt=1,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is True

    def test_scenario_client_auth_error(self):
        """Client auth errors should be terminal (no retry)."""
        category = classify_failure(status_code=401)
        assert category == FailureCategory.TERMINAL_HTTP_4XX

        policy = calculate_retry_info(
            failure_category=category,
            current_attempt=1,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is False

    def test_scenario_rate_limiting(self):
        """Rate limiting should be retryable with backoff."""
        category = classify_failure(status_code=429)
        assert category == FailureCategory.RETRYABLE_RATE_LIMIT

        policy = calculate_retry_info(
            failure_category=category,
            current_attempt=2,
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is True
        assert policy.backoff_seconds is not None

    def test_scenario_exhausted_retries(self):
        """After max retries, no more attempts should be scheduled."""
        category = classify_failure(status_code=500)
        policy = calculate_retry_info(
            failure_category=category,
            current_attempt=5,  # At max
            max_attempts=5,
            backoff_seconds_base=5,
            backoff_seconds_max=300,
        )
        assert policy.eligible is False
        assert policy.backoff_seconds is None
