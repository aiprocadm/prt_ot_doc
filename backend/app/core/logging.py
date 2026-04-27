"""Logging configuration utilities."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from logging.config import dictConfig
from typing import Any, Mapping, Sequence

from .config import get_settings
from .i18n import get_runtime_timezone
from .request_context import get_current_user_id
from .task_context import get_task_id
from .tenant import get_current_tenant
from .tracing import get_trace_id

_SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "email",
    "phone",
    "passport",
}
_EMAIL_RE = re.compile(r"(?P<local>[A-Za-z0-9._%+-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_RESERVED_LOG_RECORD_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "request_id",
    "stack_info",
    "thread",
    "threadName",
    "tenant_id",
    "trace_id",
    "user_id",
    "celery_task_id",
}
_REDACTED = "***"


def _mask_email(match: re.Match[str]) -> str:
    local = match.group("local")
    domain = match.group("domain")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _scrub_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if depth > 5:
        return _REDACTED if key and key.lower() in _SENSITIVE_KEYS else str(value)

    if isinstance(value, str):
        if key and key.lower() in _SENSITIVE_KEYS:
            return _REDACTED
        return _EMAIL_RE.sub(_mask_email, value)

    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"

    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for item_key, item_value in value.items():
            normalized_key = str(item_key)
            sanitized[normalized_key] = _scrub_value(
                item_value, key=normalized_key, depth=depth + 1
            )
        return sanitized

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [
            _scrub_value(item, key=key, depth=depth + 1)
            for item in value
        ]

    if key and key.lower() in _SENSITIVE_KEYS:
        return _REDACTED

    return value


def _stringify(value: Any) -> str:
    try:
        return str(value)
    except Exception:  # pragma: no cover - defensive
        return "<unserializable>"


class RequestContextFilter(logging.Filter):
    """Inject request context attributes into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        record.trace_id = get_trace_id()
        record.request_id = get_trace_id()
        try:
            record.tenant_id = get_current_tenant().slug
        except Exception:  # noqa: BLE001
            record.tenant_id = None
        record.user_id = get_current_user_id()
        record.celery_task_id = get_task_id()
        return True


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON with PII scrubbing."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        tz = get_runtime_timezone()
        timestamp = datetime.fromtimestamp(record.created, tz=tz).isoformat()
        trace_id = getattr(record, "trace_id", get_trace_id())

        request_id = getattr(record, "request_id", trace_id)
        tenant_id = getattr(record, "tenant_id", None)
        user_id = getattr(record, "user_id", None)
        message: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _scrub_value(record.getMessage()),
            "request_id": request_id,
            "trace_id": trace_id,
        }
        if tenant_id is not None:
            message["tenant_id"] = tenant_id
        if user_id is not None:
            message["user_id"] = user_id

        task_id = getattr(record, "celery_task_id", None)
        if task_id:
            message["task_id"] = task_id

        if record.exc_info:
            message["exc_info"] = _scrub_value(
                self.formatException(record.exc_info), key="exc_info"
            )
        if record.stack_info:
            message["stack_info"] = _scrub_value(
                self.formatStack(record.stack_info), key="stack_info"
            )

        for key, value in record.__dict__.items():
            if key.startswith("_") or key in _RESERVED_LOG_RECORD_FIELDS:
                continue
            message[key] = _scrub_value(value, key=key)

        try:
            return json.dumps(message, ensure_ascii=False, default=_stringify)
        except TypeError:
            sanitized = {k: _stringify(v) for k, v in message.items()}
            return json.dumps(sanitized, ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logging according to application settings."""

    settings = get_settings()
    formatter = "json" if settings.logging.json_enabled else "default"
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": JsonFormatter,
                },
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "filters": {"context": {"()": RequestContextFilter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": formatter,
                    "filters": ["context"],
                }
            },
            "root": {
                "handlers": ["console"],
                "level": settings.logging.level,
            },
        }
    )


__all__ = ["JsonFormatter", "RequestContextFilter", "configure_logging"]
