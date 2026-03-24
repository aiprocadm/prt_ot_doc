"""
Correlation ID and request tracing helpers.

Ensures correlation_id propagates through all layers:
- HTTP requests
- Background jobs
- Logging context
- Service calls
"""

import contextvars
import logging
from typing import Optional

# Context variable for correlation_id (thread-local alternative)
_correlation_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


class CorrelationIDManager:
    """Manages correlation ID across request lifecycle and background jobs."""

    @staticmethod
    def set(correlation_id: str) -> None:
        """Set correlation ID for current context."""
        _correlation_id_context.set(correlation_id)

    @staticmethod
    def get() -> Optional[str]:
        """Get correlation ID from current context."""
        return _correlation_id_context.get()

    @staticmethod
    def clear() -> None:
        """Clear correlation ID from current context."""
        _correlation_id_context.set(None)

    @staticmethod
    def copy_context():
        """Copy context for background job execution."""
        return contextvars.copy_context()


class CorrelationIDLogger:
    """Logger that includes correlation_id in all messages."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _get_extra(self, extra: dict | None = None) -> dict:
        """Build extra dict with correlation_id."""
        result = extra or {}
        correlation_id = CorrelationIDManager.get()
        if correlation_id:
            result["correlation_id"] = correlation_id
        return result

    def debug(self, msg: str, *args, extra: dict | None = None, **kwargs):
        """Log debug with correlation_id."""
        self.logger.debug(msg, *args, extra=self._get_extra(extra), **kwargs)

    def info(self, msg: str, *args, extra: dict | None = None, **kwargs):
        """Log info with correlation_id."""
        self.logger.info(msg, *args, extra=self._get_extra(extra), **kwargs)

    def warning(self, msg: str, *args, extra: dict | None = None, **kwargs):
        """Log warning with correlation_id."""
        self.logger.warning(msg, *args, extra=self._get_extra(extra), **kwargs)

    def error(self, msg: str, *args, extra: dict | None = None, **kwargs):
        """Log error with correlation_id."""
        self.logger.error(msg, *args, extra=self._get_extra(extra), **kwargs)

    def critical(self, msg: str, *args, extra: dict | None = None, **kwargs):
        """Log critical with correlation_id."""
        self.logger.critical(msg, *args, extra=self._get_extra(extra), **kwargs)


def get_logger(name: str) -> CorrelationIDLogger:
    """Get correlation-aware logger."""
    return CorrelationIDLogger(name)
