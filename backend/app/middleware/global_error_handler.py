"""
Global error handling middleware.

Catches all exceptions and returns standardized error responses
aligned with :mod:`app.api.error_handlers`.
"""

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.error_handlers import json_error_response_for_request
from app.core.correlation_id import CorrelationIDManager, get_logger

logger = get_logger(__name__)


class GlobalErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global middleware for standardized error handling."""

    @staticmethod
    def _classify_value_error(exc: ValueError) -> tuple[int, str]:
        message = str(exc).strip().lower()
        if any(token in message for token in ("tenant", "x-tenant", "missing_tenant")):
            return status.HTTP_400_BAD_REQUEST, "TENANT_INVALID"
        if "permission" in message:
            return status.HTTP_403_FORBIDDEN, "PERMISSION_DENIED"
        return status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR"

    async def dispatch(self, request: Request, call_next):
        """Catch exceptions and return standardized error responses."""
        try:
            # Extract correlation_id from headers and set in context
            correlation_id = request.headers.get(
                "x-correlation-id"
            ) or request.headers.get("x-request-id") or getattr(request.state, "correlation_id", None)
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

    def _handle_value_error(self, exc: ValueError, request: Request):
        """Handle ValueError (validation, tenant context, etc.)."""
        error_message = str(exc)
        status_code, error_code = self._classify_value_error(exc)

        logger.warning(
            f"Validation error: {error_message}",
            extra={
                "error_code": error_code,
                "request_path": request.url.path,
                "method": request.method,
            },
        )

        return json_error_response_for_request(
            request,
            status_code=status_code,
            code=error_code,
            message=error_message,
            details={"source": "ValueError"},
        )

    def _handle_permission_error(self, exc: PermissionError, request: Request):
        """Handle PermissionError."""
        logger.warning(
            f"Permission denied: {str(exc)}",
            extra={
                "request_path": request.url.path,
                "method": request.method,
            },
        )

        return json_error_response_for_request(
            request,
            status_code=status.HTTP_403_FORBIDDEN,
            code="PERMISSION_DENIED",
            message=str(exc),
            details={"source": "PermissionError"},
        )

    def _handle_unexpected_error(self, exc: Exception, request: Request):
        """Handle unexpected exceptions."""
        logger.error(
            f"Unexpected error: {str(exc)}",
            exc_info=exc,
            extra={
                "request_path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
            },
        )

        return json_error_response_for_request(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            message="Internal server error",
            details={},
        )
