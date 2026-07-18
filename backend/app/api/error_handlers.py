"""Unified error handling for the public API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any, Final, Mapping

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps.tracing import TRACE_HEADER as DEFAULT_TRACE_HEADER
from app.api.deps.tracing import get_trace_id
from app.core.config import Settings, get_settings

try:  # pragma: no cover - optional dependency during docs builds
    from slowapi.errors import RateLimitExceeded
except ImportError:  # pragma: no cover - optional dependency
    RateLimitExceeded = None  # type: ignore[assignment]


LOGGER = logging.getLogger(__name__)
TRACE_HEADER: Final[str] = DEFAULT_TRACE_HEADER
JSON_MEDIA_TYPE = "application/json"


@dataclass(slots=True)
class ErrorPayload:
    code: str
    error_type: str
    message: str
    details: Mapping[str, Any] | None
    field_errors: list[dict[str, Any]]
    trace_id: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "error_code": self.code,
            "type": self.error_type,
            "message": self.message,
            "trace_id": self.trace_id,
            "request_id": self.trace_id,
            "correlation_id": self.trace_id,
            "timestamp": self.timestamp,
            "field_errors": self.field_errors,
        }
        if self.details:
            payload["details"] = dict(self.details)
        else:
            payload["details"] = {}
        return payload


def _status_message(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:  # pragma: no cover - defensive fallback
        return "HTTP Error"


def _extract_message_and_details(exc: StarletteHTTPException) -> tuple[str, Mapping[str, Any]]:
    detail = exc.detail
    if isinstance(detail, Mapping):
        message = str(
            detail.get("message") or detail.get("detail") or _status_message(exc.status_code)
        )
        return message, detail
    if isinstance(detail, list):
        return _status_message(exc.status_code), {"errors": detail}
    if detail:
        return str(detail), {}
    return _status_message(exc.status_code), {}


def _resolve_error_code(status_code: int) -> str:
    """Машинный код ошибки в стиле SCREAMING_SNAKE (единый контракт API)."""

    if status.HTTP_500_INTERNAL_SERVER_ERROR <= status_code < 600:
        return "INTERNAL_ERROR"
    mapping: dict[int, str] = {
        status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
        status.HTTP_402_PAYMENT_REQUIRED: "PAYMENT_REQUIRED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_408_REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_410_GONE: "GONE",
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: "PAYLOAD_TOO_LARGE",
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "UNSUPPORTED_MEDIA_TYPE",
        status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
        status.HTTP_429_TOO_MANY_REQUESTS: "TOO_MANY_REQUESTS",
        status.HTTP_502_BAD_GATEWAY: "BAD_GATEWAY",
        status.HTTP_503_SERVICE_UNAVAILABLE: "SERVICE_UNAVAILABLE",
        status.HTTP_504_GATEWAY_TIMEOUT: "GATEWAY_TIMEOUT",
    }
    return mapping.get(status_code, f"HTTP_{status_code}")


def _resolve_error_type(status_code: int, details: Mapping[str, Any] | None = None) -> str:
    if details:
        candidate = details.get("type")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    if status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}:
        return "security"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    if status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return "validation"
    if status.HTTP_400_BAD_REQUEST <= status_code < 500:
        return "business"
    return "server"


def _extract_field_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for error in errors:
        location = error.get("loc")
        if isinstance(location, (list, tuple)):
            field = ".".join(str(part) for part in location if part != "body")
        else:
            field = str(location or "")
        normalized.append(
            {
                "field": field or None,
                "message": str(error.get("msg") or "Invalid value"),
                "type": str(error.get("type") or "validation_error"),
            }
        )
    return normalized


def _json_safe(value: Any) -> Any:
    """Recursively coerce *value* into JSON-serializable primitives.

    Pydantic v2 embeds raw exception objects in ``exc.errors()`` — e.g. the
    ``ValueError`` raised by a ``@model_validator`` lands under ``ctx["error"]``.
    Such objects break :class:`JSONResponse` rendering with
    ``TypeError: Object of type ValueError is not JSON serializable``, so any
    non-primitive leaf is stringified before it reaches the encoder.
    """

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _is_json_payload_error(exc: RequestValidationError) -> bool:
    json_error_types = {"json_invalid", "type_error.jsondecode"}
    for error in exc.errors():
        if error.get("type") in json_error_types:
            return True
    return False


def _build_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None,
    field_errors: list[dict[str, Any]] | None,
    trace_id: str,
    trace_header: str,
    headers: Mapping[str, str] | None = None,
    detail_payload: Any | None = None,
    error_type: str | None = None,
) -> JSONResponse:
    resolved_error_type = (
        error_type if error_type is not None else _resolve_error_type(status_code, details)
    )
    payload = ErrorPayload(
        code=code,
        error_type=resolved_error_type,
        message=message,
        details=details,
        field_errors=field_errors or [],
        trace_id=trace_id,
        timestamp=datetime.now(UTC).isoformat(),
    ).to_dict()
    if detail_payload is not None:
        payload["detail"] = detail_payload
    response_headers = {
        trace_header: trace_id,
        "X-Trace-Id": trace_id,
        "X-Correlation-Id": trace_id,
        "X-Request-Id": trace_id,
    }
    if headers:
        response_headers.update(headers)
    return JSONResponse(status_code=status_code, content=payload, headers=response_headers)


async def _enforce_json_limit(
    request: Request,
    *,
    settings: Settings,
    trace_id: str,
    trace_header: str,
) -> Response | None:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != JSON_MEDIA_TYPE:
        return None

    body = await request.body()
    if len(body) <= settings.json_max_bytes:
        return None

    LOGGER.warning(
        "json.payload.too_large",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "size": len(body),
            "limit": settings.json_max_bytes,
        },
    )
    mebibytes = max(1, settings.json_max_bytes // (1024 * 1024))
    message = f"JSON payload exceeds {mebibytes} MiB limit"
    details = {"limit": settings.json_max_bytes, "size": len(body)}
    return _build_response(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        code="PAYLOAD_TOO_LARGE",
        message=message,
        details=details,
        field_errors=[],
        trace_id=trace_id,
        trace_header=trace_header,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register middleware and handlers that normalize error payloads."""

    settings = getattr(app.state, "settings", None) or get_settings()
    trace_header = settings.trace_header_name

    @app.middleware("http")
    async def _error_middleware(request: Request, call_next) -> Response:
        trace_id = get_trace_id(request, trace_header)

        json_limit_response = await _enforce_json_limit(
            request,
            settings=settings,
            trace_id=trace_id,
            trace_header=trace_header,
        )
        if json_limit_response is not None:
            return json_limit_response

        try:
            response = await call_next(request)
        except (HTTPException, StarletteHTTPException) as exc:
            if RateLimitExceeded is not None and isinstance(exc, RateLimitExceeded):
                raise
            return _handle_http_exception(request, exc, trace_id, trace_header)
        except RequestValidationError as exc:
            return _handle_validation_error(request, exc, trace_id, trace_header)
        except Exception as exc:  # noqa: BLE001 - top-level safeguard
            return _handle_unexpected_exception(request, exc, trace_id, trace_header)

        response.headers.setdefault(trace_header, trace_id)
        response.headers.setdefault("X-Trace-Id", trace_id)
        response.headers.setdefault("X-Correlation-Id", trace_id)
        response.headers.setdefault("X-Request-Id", trace_id)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(  # type: ignore[override]
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        trace_id = get_trace_id(request, trace_header)
        return _handle_validation_error(request, exc, trace_id, trace_header)

    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(  # type: ignore[override]
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        trace_id = get_trace_id(request, trace_header)
        return _handle_http_exception(request, exc, trace_id, trace_header)

    if RateLimitExceeded is not None:

        @app.exception_handler(RateLimitExceeded)
        async def _rate_limit_exception_handler(  # type: ignore[override]
            request: Request,
            exc: RateLimitExceeded,
        ) -> JSONResponse:
            trace_id = get_trace_id(request, trace_header)
            message, details = _extract_message_and_details(exc)
            if not message:
                message = "Rate limit exceeded"
            return _build_response(
                status_code=exc.status_code,
                code="RATE_LIMIT_EXCEEDED",
                message=message,
                details=details,
                field_errors=[],
                trace_id=trace_id,
                trace_header=trace_header,
                headers=exc.headers,
            )


def _handle_validation_error(
    request: Request,
    exc: RequestValidationError,
    trace_id: str,
    trace_header: str,
) -> JSONResponse:
    errors = _json_safe(exc.errors())
    details = {"errors": errors}
    field_errors = _extract_field_errors(errors)
    if _is_json_payload_error(exc):
        message = "Invalid JSON payload"
        code = "INVALID_JSON"
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        message = "Request validation failed"
        code = "VALIDATION_ERROR"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    LOGGER.info(
        "request.validation_error",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "method": request.method,
            "errors": errors,
        },
    )
    return _build_response(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        field_errors=field_errors,
        trace_id=trace_id,
        trace_header=trace_header,
        detail_payload=errors,
    )


def _handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
    trace_id: str,
    trace_header: str,
) -> JSONResponse:
    message, details = _extract_message_and_details(exc)
    custom_details: Mapping[str, Any] | None = details
    field_errors: list[dict[str, Any]] = []
    code_override: str | None = None
    error_type_override: str | None = None

    if isinstance(details, Mapping):
        mutable = dict(details)
        candidate = mutable.get("code") or mutable.get("error_code")
        if isinstance(candidate, str) and candidate.strip():
            code_override = candidate.strip()
            mutable.pop("code", None)
            mutable.pop("error_code", None)
        if mutable.get("message") == message:
            mutable.pop("message")
        if mutable.get("detail") == message:
            mutable.pop("detail")
        raw_field_errors = mutable.pop("field_errors", [])
        if isinstance(raw_field_errors, list):
            field_errors = [item for item in raw_field_errors if isinstance(item, dict)]
        legacy_field = mutable.pop("field", None)
        if isinstance(legacy_field, str) and legacy_field.strip() and not field_errors:
            field_errors = [
                {
                    "field": legacy_field.strip(),
                    "message": message,
                    "type": "validation_error",
                }
            ]
        error_type_override = _resolve_error_type(exc.status_code, mutable)
        for drop in ("correlation_id", "timestamp", "type"):
            mutable.pop(drop, None)
        custom_details = mutable

    code = code_override or _resolve_error_code(exc.status_code)

    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        LOGGER.error(
            "request.http_exception",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "error_message": message,
            },
        )
    else:
        LOGGER.info(
            "request.http_exception",
            extra={
                "trace_id": trace_id,
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
            },
        )
    return _build_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        details=custom_details,
        field_errors=field_errors,
        trace_id=trace_id,
        trace_header=trace_header,
        headers=exc.headers,
        detail_payload=exc.detail,
        error_type=error_type_override,
    )


def _handle_unexpected_exception(
    request: Request,
    exc: Exception,
    trace_id: str,
    trace_header: str,
) -> JSONResponse:
    LOGGER.exception(
        "request.unhandled_exception",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return _build_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="Internal server error",
        details={},
        field_errors=[],
        trace_id=trace_id,
        trace_header=trace_header,
    )


def json_error_response_for_request(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    field_errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Публичный JSON-ответ с телом контракта :mod:`app.api.error_handlers` (для middleware и утилит)."""

    settings = getattr(request.app.state, "settings", None) or get_settings()
    trace_header = settings.trace_header_name
    trace_id = get_trace_id(request, trace_header)
    return _build_response(
        status_code=status_code,
        code=code,
        message=message,
        details=dict(details) if details else {},
        field_errors=field_errors or [],
        trace_id=trace_id,
        trace_header=trace_header,
    )


__all__ = ["register_exception_handlers", "TRACE_HEADER", "json_error_response_for_request"]
