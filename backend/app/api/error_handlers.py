"""Unified error handling for the public API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Final, Mapping

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps.tracing import TRACE_HEADER as DEFAULT_TRACE_HEADER, get_trace_id
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
    message: str
    details: Mapping[str, Any] | None
    trace_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "error_code": self.code,
            "message": self.message,
            "trace_id": self.trace_id,
            "request_id": self.trace_id,
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
        message = str(detail.get("message") or detail.get("detail") or _status_message(exc.status_code))
        return message, detail
    if isinstance(detail, list):
        return _status_message(exc.status_code), {"errors": detail}
    if detail:
        return str(detail), {}
    return _status_message(exc.status_code), {}


def _resolve_error_code(status_code: int) -> str:
    if status_code == status.HTTP_403_FORBIDDEN:
        return "forbidden"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    if status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        return "validation_error"
    if status.HTTP_400_BAD_REQUEST <= status_code < 500:
        return f"http_{status_code}"
    return "internal"


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
    trace_id: str,
    trace_header: str,
    headers: Mapping[str, str] | None = None,
    detail_payload: Any | None = None,
) -> JSONResponse:
    payload = ErrorPayload(
        code=code,
        message=message,
        details=details,
        trace_id=trace_id,
    ).to_dict()
    if detail_payload is not None:
        payload["detail"] = detail_payload
    response_headers = {trace_header: trace_id, "X-Trace-Id": trace_id}
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
        code="payload_too_large",
        message=message,
        details=details,
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
                code="rate_limit_exceeded",
                message=message,
                details=details,
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
    details = {"errors": exc.errors()}
    if _is_json_payload_error(exc):
        message = "Invalid JSON payload"
        code = "invalid_json"
        status_code = status.HTTP_400_BAD_REQUEST
    else:
        message = "Request validation failed"
        code = "validation_error"
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    LOGGER.info(
        "request.validation_error",
        extra={
            "trace_id": trace_id,
            "path": request.url.path,
            "method": request.method,
            "errors": exc.errors(),
        },
    )
    return _build_response(
        status_code=status_code,
        code=code,
        message=message,
        details=details,
        trace_id=trace_id,
        trace_header=trace_header,
        detail_payload=exc.errors(),
    )


def _handle_http_exception(
    request: Request,
    exc: StarletteHTTPException,
    trace_id: str,
    trace_header: str,
) -> JSONResponse:
    message, details = _extract_message_and_details(exc)
    custom_details: Mapping[str, Any] | None = details
    code_override: str | None = None

    if isinstance(details, Mapping):
        mutable = dict(details)
        candidate = mutable.get("code")
        if isinstance(candidate, str) and candidate.strip():
            code_override = mutable.pop("code", None)
        if mutable.get("message") == message:
            mutable.pop("message")
        if mutable.get("detail") == message:
            mutable.pop("detail")
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
        trace_id=trace_id,
        trace_header=trace_header,
        headers=exc.headers,
        detail_payload=exc.detail,
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
        code="internal",
        message="Internal Server Error",
        details={},
        trace_id=trace_id,
        trace_header=trace_header,
    )


__all__ = ["register_exception_handlers", "TRACE_HEADER"]
