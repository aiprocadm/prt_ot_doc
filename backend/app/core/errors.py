"""
Standardized error handling and response formatting.

This module provides centralized error envelope format for all endpoints,
ensuring consistency in error responses, correlation_id propagation, and error messaging.
"""

from typing import Any

from fastapi import status
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Standard error response envelope."""

    error_code: str
    """Machine-readable error code (e.g., 'TENANT_REQUIRED', 'PERMISSION_DENIED')."""

    message: str
    """Human-readable error message."""

    field: str | None = None
    """Optional field name (for validation errors)."""

    details: dict[str, Any] | None = None
    """Optional additional context."""

    correlation_id: str | None = None
    """Request correlation ID for tracing."""

    timestamp: str | None = None
    """ISO 8601 timestamp of error."""

    class Config:
        json_schema_extra = {
            "example": {
                "error_code": "PERMISSION_DENIED",
                "message": "User does not have permission to perform this action",
                "field": None,
                "correlation_id": "req_12345",
                "timestamp": "2026-03-24T10:30:00Z",
            }
        }


class ErrorBuilder:
    """Builder for standardized error responses."""

    def __init__(self):
        self.error_code: str | None = None
        self.message: str | None = None
        self.field: str | None = None
        self.details: dict[str, Any] | None = None
        self.correlation_id: str | None = None
        self.timestamp: str | None = None

    def with_code(self, code: str) -> "ErrorBuilder":
        """Set error code."""
        self.error_code = code
        return self

    def with_message(self, message: str) -> "ErrorBuilder":
        """Set error message."""
        self.message = message
        return self

    def with_field(self, field: str) -> "ErrorBuilder":
        """Set field name (for validation errors)."""
        self.field = field
        return self

    def with_details(self, details: dict[str, Any]) -> "ErrorBuilder":
        """Set additional details."""
        self.details = details
        return self

    def with_correlation_id(self, correlation_id: str) -> "ErrorBuilder":
        """Set correlation ID."""
        self.correlation_id = correlation_id
        return self

    def with_timestamp(self, timestamp: str) -> "ErrorBuilder":
        """Set timestamp."""
        self.timestamp = timestamp
        return self

    def build(self) -> ErrorDetail:
        """Build error detail."""
        if not self.error_code or not self.message:
            raise ValueError("error_code and message are required")
        return ErrorDetail(
            error_code=self.error_code,
            message=self.message,
            field=self.field,
            details=self.details,
            correlation_id=self.correlation_id,
            timestamp=self.timestamp,
        )


# Standard error codes
ERROR_CODES = {
    # Tenancy errors
    "TENANT_REQUIRED": (status.HTTP_400_BAD_REQUEST, "Missing required X-Tenant header"),
    "TENANT_INVALID": (status.HTTP_400_BAD_REQUEST, "Invalid tenant identifier"),
    "TENANT_INACTIVE": (status.HTTP_403_FORBIDDEN, "Tenant is inactive"),
    "TENANT_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Tenant not found"),
    # Permission errors
    "PERMISSION_DENIED": (status.HTTP_403_FORBIDDEN, "User does not have permission"),
    "AUTHENTICATION_REQUIRED": (status.HTTP_401_UNAUTHORIZED, "Authentication required"),
    "UNAUTHORIZED": (status.HTTP_401_UNAUTHORIZED, "Unauthorized"),
    # Resource errors
    "NOT_FOUND": (status.HTTP_404_NOT_FOUND, "Resource not found"),
    "CONFLICT": (status.HTTP_409_CONFLICT, "Resource already exists or conflict"),
    "VALIDATION_ERROR": (status.HTTP_400_BAD_REQUEST, "Validation error"),
    # Server errors
    "INTERNAL_ERROR": (status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error"),
}


def get_default_message(error_code: str) -> str:
    """Get default message for error code."""
    return ERROR_CODES.get(error_code, ("Unknown error", status.HTTP_500_INTERNAL_SERVER_ERROR))[1]


def get_status_code(error_code: str) -> int:
    """Get HTTP status code for error code."""
    return ERROR_CODES.get(error_code, (status.HTTP_500_INTERNAL_SERVER_ERROR, "Unknown"))[0]
