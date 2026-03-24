"""Tests for Phase 2 consistency foundation helpers."""

import pytest
from fastapi import HTTPException, status

from app.core.correlation_id import CorrelationIDManager, get_logger
from app.core.errors import ErrorBuilder, ErrorDetail, ERROR_CODES
from app.core.permission_checker import PermissionAction, PermissionChecker
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant


class TestErrorBuilder:
    """Tests for ErrorBuilder."""

    def test_build_complete_error(self):
        """Test building complete error with all fields."""
        error = (
            ErrorBuilder()
            .with_code("TEST_ERROR")
            .with_message("Test error message")
            .with_field("test_field")
            .with_details({"key": "value"})
            .with_correlation_id("corr-123")
            .with_timestamp("2026-03-24T10:30:00Z")
            .build()
        )

        assert isinstance(error, ErrorDetail)
        assert error.error_code == "TEST_ERROR"
        assert error.message == "Test error message"
        assert error.field == "test_field"
        assert error.details == {"key": "value"}
        assert error.correlation_id == "corr-123"
        assert error.timestamp == "2026-03-24T10:30:00Z"

    def test_build_minimal_error(self):
        """Test building error with only required fields."""
        error = (
            ErrorBuilder()
            .with_code("MINIMAL")
            .with_message("Minimal error")
            .build()
        )

        assert error.error_code == "MINIMAL"
        assert error.message == "Minimal error"
        assert error.field is None
        assert error.details is None

    def test_build_missing_code_raises(self):
        """Test that missing code raises ValueError."""
        with pytest.raises(ValueError):
            ErrorBuilder().with_message("No code").build()

    def test_build_missing_message_raises(self):
        """Test that missing message raises ValueError."""
        with pytest.raises(ValueError):
            ErrorBuilder().with_code("NO_MESSAGE").build()

    def test_error_codes_dict(self):
        """Test ERROR_CODES dict has standard entries."""
        assert "TENANT_REQUIRED" in ERROR_CODES
        assert "PERMISSION_DENIED" in ERROR_CODES
        assert "NOT_FOUND" in ERROR_CODES
        assert "INTERNAL_ERROR" in ERROR_CODES

        # Check structure
        code, message = ERROR_CODES["PERMISSION_DENIED"]
        assert code == status.HTTP_403_FORBIDDEN
        assert isinstance(message, str)


class TestPermissionChecker:
    """Tests for PermissionChecker."""

    def test_check_permitted(self):
        """Test check passes when permission granted."""
        # Should not raise
        PermissionChecker.check(
            has_permission=True,
            action="write",
            resource="document",
            correlation_id="corr-123",
        )

    def test_check_denied_raises(self):
        """Test check raises HTTPException when denied."""
        with pytest.raises(HTTPException) as exc_info:
            PermissionChecker.check(
                has_permission=False,
                action="delete",
                resource="user",
                correlation_id="corr-456",
            )

        exc = exc_info.value
        assert exc.status_code == status.HTTP_403_FORBIDDEN
        detail = exc.detail
        assert detail["error_code"] == "PERMISSION_DENIED"
        assert "delete" in detail["message"].lower()
        assert detail["correlation_id"] == "corr-456"

    def test_check_any_any_permitted(self):
        """Test check_any passes if any permission granted."""
        PermissionChecker.check_any(
            permissions=[False, True, False],
            action="read",
            resource="report",
        )

    def test_check_any_none_permitted_raises(self):
        """Test check_any raises if all permissions denied."""
        with pytest.raises(HTTPException) as exc_info:
            PermissionChecker.check_any(
                permissions=[False, False, False],
                action="export",
                resource="data",
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_check_all_all_permitted(self):
        """Test check_all passes if all permissions granted."""
        PermissionChecker.check_all(
            permissions=[True, True, True],
            action="admin",
            resource="tenant",
        )

    def test_check_all_one_denied_raises(self):
        """Test check_all raises if any permission denied."""
        with pytest.raises(HTTPException) as exc_info:
            PermissionChecker.check_all(
                permissions=[True, False, True],
                action="modify",
                resource="config",
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    def test_permission_action_enum(self):
        """Test PermissionAction enum values."""
        assert PermissionAction.READ.value == "read"
        assert PermissionAction.WRITE.value == "write"
        assert PermissionAction.DELETE.value == "delete"
        assert PermissionAction.ADMIN.value == "admin"
        assert PermissionAction.EXPORT.value == "export"
        assert PermissionAction.BULK.value == "bulk"


class TestTenantContextValidator:
    """Tests for TenantContextValidator."""

    def test_ensure_tenant_context_valid(self):
        """Test ensure_tenant_context passes for valid tenant."""
        tenant = Tenant(id="123", slug="test-tenant", is_active=True)
        result = TenantContextValidator.ensure_tenant_context(tenant)
        assert result == tenant

    def test_ensure_tenant_context_none_raises(self):
        """Test ensure_tenant_context raises for None tenant."""
        with pytest.raises(ValueError, match="Tenant context required"):
            TenantContextValidator.ensure_tenant_context(None)

    def test_ensure_tenant_context_inactive_raises(self):
        """Test ensure_tenant_context raises for inactive tenant."""
        tenant = Tenant(id="123", slug="test", is_active=False)
        with pytest.raises(ValueError, match="inactive"):
            TenantContextValidator.ensure_tenant_context(tenant)

    def test_ensure_session_tenant_match(self):
        """Test ensure_session_tenant passes if session tenant matches."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import MagicMock

        session = MagicMock(spec=AsyncSession)
        session.info = {"tenant": "test-tenant"}

        # Should not raise
        TenantContextValidator.ensure_session_tenant(session, "test-tenant")

    def test_ensure_session_tenant_mismatch_raises(self):
        """Test ensure_session_tenant raises on mismatch."""
        from sqlalchemy.ext.asyncio import AsyncSession
        from unittest.mock import MagicMock

        session = MagicMock(spec=AsyncSession)
        session.info = {"tenant": "tenant-a"}

        with pytest.raises(ValueError, match="mismatch"):
            TenantContextValidator.ensure_session_tenant(session, "tenant-b")

    def test_build_tenant_error(self):
        """Test build_tenant_error creates proper error response."""
        error = TenantContextValidator.build_tenant_error(
            "TENANT_REQUIRED",
            correlation_id="corr-789",
            details={"hint": "Set X-Tenant header"},
        )

        assert error["error_code"] == "TENANT_REQUIRED"
        assert error["correlation_id"] == "corr-789"
        assert error["details"]["hint"] == "Set X-Tenant header"


class TestCorrelationIDManager:
    """Tests for CorrelationIDManager."""

    def test_set_and_get(self):
        """Test setting and getting correlation ID."""
        CorrelationIDManager.set("test-123")
        assert CorrelationIDManager.get() == "test-123"

    def test_clear(self):
        """Test clearing correlation ID."""
        CorrelationIDManager.set("test-456")
        CorrelationIDManager.clear()
        assert CorrelationIDManager.get() is None

    def test_default_none(self):
        """Test default is None before set."""
        CorrelationIDManager.clear()
        assert CorrelationIDManager.get() is None

    def test_copy_context(self):
        """Test copying context."""
        CorrelationIDManager.set("ctx-123")
        ctx = CorrelationIDManager.copy_context()
        assert ctx is not None
        # Context should have correlation_id value captured


class TestCorrelationIDLogger:
    """Tests for CorrelationIDLogger."""

    def test_get_logger(self):
        """Test get_logger returns logger."""
        logger = get_logger(__name__)
        assert logger is not None
        assert hasattr(logger, "info")
        assert hasattr(logger, "warning")
        assert hasattr(logger, "error")

    def test_logger_includes_correlation_id(self, caplog):
        """Test logger includes correlation_id in logs."""
        import logging

        caplog.set_level(logging.INFO)
        CorrelationIDManager.set("log-test-123")

        logger = get_logger("test_logger")
        logger.info("Test message")

        # Check that info dict includes correlation_id
        assert len(caplog.records) > 0
        record = caplog.records[0]
        assert record.correlation_id == "log-test-123"

    def test_logger_without_correlation_id(self, caplog):
        """Test logger works without correlation_id set."""
        import logging

        caplog.set_level(logging.INFO)
        CorrelationIDManager.clear()

        logger = get_logger("test_logger_2")
        logger.info("Message without correlation_id")

        # Should not crash, just not include correlation_id
        assert len(caplog.records) > 0


class TestErrorCodes:
    """Tests for ERROR_CODES utility."""

    def test_error_codes_completeness(self):
        """Test all expected error codes are present."""
        expected_codes = [
            "TENANT_REQUIRED",
            "TENANT_INVALID",
            "TENANT_INACTIVE",
            "TENANT_NOT_FOUND",
            "PERMISSION_DENIED",
            "AUTHENTICATION_REQUIRED",
            "UNAUTHORIZED",
            "NOT_FOUND",
            "CONFLICT",
            "VALIDATION_ERROR",
            "INTERNAL_ERROR",
        ]

        for code in expected_codes:
            assert code in ERROR_CODES, f"Missing error code: {code}"

    def test_error_codes_structure(self):
        """Test all error codes have valid (status_code, message) tuple."""
        for code, (status_code, message) in ERROR_CODES.items():
            assert isinstance(status_code, int), f"{code}: status_code not int"
            assert 100 <= status_code < 600, f"{code}: invalid status code"
            assert isinstance(message, str), f"{code}: message not string"
            assert len(message) > 0, f"{code}: empty message"


# Integration-style tests

class TestConsistencyIntegration:
    """Integration tests for consistency helpers."""

    def test_permission_denied_with_error_builder(self):
        """Test PermissionChecker integrates with ErrorBuilder."""
        with pytest.raises(HTTPException) as exc_info:
            PermissionChecker.check(
                False,
                action="write",
                resource="document",
                correlation_id="integ-123",
            )

        exc = exc_info.value
        assert exc.status_code == 403
        # Detail should include all error fields
        assert "error_code" in exc.detail
        assert "correlation_id" in exc.detail

    def test_tenant_validation_with_correlation_id(self):
        """Test TenantContextValidator with correlation_id."""
        error = TenantContextValidator.build_tenant_error(
            "TENANT_INACTIVE",
            correlation_id="tenant-test-123",
        )

        assert error["error_code"] == "TENANT_INACTIVE"
        assert error["correlation_id"] == "tenant-test-123"
        assert "inactive" in error["message"].lower()
