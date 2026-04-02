"""Application logging configuration utilities."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JsonLogFormatter(logging.Formatter):
    """Formatter that outputs structured JSON logs suitable for production."""

    default_fields = {"name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process"}

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "message": record.getMessage(),
            "logger": record.name,
        }

        for key, value in record.__dict__.items():
            if key in self.default_fields:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str | int = logging.INFO) -> None:
    """Configure root logger with JSON formatter."""
    root_logger = logging.getLogger()
    # Avoid duplicate handlers when configure_logging is called multiple times.
    if root_logger.handlers:
        root_logger.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonLogFormatter())

    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Ensure libraries respect our configuration.
    logging.captureWarnings(True)
