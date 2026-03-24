"""
Global error handling middleware.

Catches all exceptions and returns standardized error responses
with correlation_id and structured format.
"""

import logging
from datetime import datetime, timezone

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.correlation_id import CorrelationIDManager, get_logger
from app.core.errors import ErrorBuilder, get_status_code

logger = get_logger(__name__)


class GlobalErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global middleware for standardized error handling."""

    async def dispatch(self, request: Request, call_next):
        """Catch exceptions and return standardized error responses."""
        try:
            # Extract correlation_id from headers and set in context
            correlation_id = request.headers.get(
                "x-correlation-id"
            ) or request.headers.get("x-request-id")
            if correlation_id:
                CorrelationIDManager.set(correlation_id)

            response = await call_next(request)
            return response

        except ValueError as exc:
            # Handle validation errors
            return self._handle_value_error(exc, request)
        except PermissionError as exc:
            # Handle permission errors
            return self._handle_permission_error(exc, request)
        except Exception as exc:
            # Handle unexpected errors
            return self._handle_unexpected_error(exc, request)

    def _handle_value_error(self, exc: ValueError, request: Request) -> JSONResponse:
        """Handle ValueError (validation, tenant context, etc.)."""
        correlation_id = CorrelationIDManager.get()

        error_message = str(exc)
        error_code = "VALIDATION_ERROR"

        if "tenant" in error_message.lower():
            error_code = "TENANT_INVALID"
            status_code = status.HTTP_400_BAD_REQUEST
        elif "permission" in error_message.lower():
            error_code = "PERMISSION_DENIED"
            status_code = status.HTTP_403_FORBIDDEN
        else:
            status_code = status.HTTP_400_BAD_REQUEST

        logger.warning(
            f"Validation error: {error_message}",
            extra={
                "error_code": error_code,
                "request_path": request.url.path,
                "method": request.method,
            },
        )

        error = (
            ErrorBuilder()
            .with_code(error_code)
            .with_message(error_message)
            .with_correlation_id(correlation_id)
            .with_timestamp(datetime.now(timezone.utc).isoformat())
            .build()
        )

        return JSONResponse(
            status_code=status_code,
            content=error.model_dump(),
            headers={"X-Correlation-Id": correlation_id or "unknown"},
        )

    def _handle_permission_error(self, exc: PermissionError, request: Request) -> JSONResponse:
        """Handle PermissionError."""
        correlation_id = CorrelationIDManager.get()

        logger.warning(
            f"Permission denied: {str(exc)}",
            extra={
                "request_path": request.url.path,
                "method": request.method,
            },
        )

        error = (
            ErrorBuilder()
            .with_code("PERMISSION_DENIED")
            .with_message(str(exc))
            .with_correlation_id(correlation_id)
            .with_timestamp(datetime.now(timezone.utc).isoformat())
            .build()
        )

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=error.model_dump(),
            headers={"X-Correlation-Id": correlation_id or "unknown"},
        )

    def _handle_unexpected_error(self, exc: Exception, request: Request) -> JSONResponse:
        """Handle unexpected exceptions."""
        correlation_id = CorrelationIDManager.get()

        logger.error(
            f"Unexpected error: {str(exc)}",
            exc_info=exc,
            extra={
                "request_path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
            },
        )

        error = (
            ErrorBuilder()
            .with_code("INTERNAL_ERROR")
            .with_message("Internal server error")
            .with_details({"correlation_id": correlation_id, "error_type": type(exc).__name__})
            .with_correlation_id(correlation_id)
            .with_timestamp(datetime.now(timezone.utc).isoformat())
            .build()
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error.model_dump(),
            headers={"X-Correlation-Id": correlation_id or "unknown"},
        )
