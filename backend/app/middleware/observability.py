"""Middleware for enforcing request limits and observability hooks."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from starlette import status
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.metrics import get_metrics
from app.core.request_context import reset_current_user_id, set_current_user_id
from app.core.tracing import reset_trace_id, set_trace_id


class _BodyTooLargeError(Exception):
    """Raised when a request body exceeds configured limits."""


class ObservabilityMiddleware:
    """ASGI middleware enforcing body limits, timeouts and metrics."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self._max_body_bytes = settings.max_request_body_bytes
        self._timeout_seconds = settings.request_timeout_seconds
        self._trace_header = settings.trace_header_name
        self._metrics_enabled = settings.enable_metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        trace_header_value = headers.get(self._trace_header)
        trace_id = self._select_trace_id(trace_header_value)
        trace_token = set_trace_id(trace_id)
        user_token = set_current_user_id(None)
        self._store_trace_in_scope(scope, trace_id)
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")
        route_path = path
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response_started = False
        start_time = time.perf_counter()
        metrics = get_metrics() if self._metrics_enabled else None

        try:
            if self._should_reject_by_header(headers):
                status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
                await self._send_error_response(
                    scope,
                    send,
                    status_code=status_code,
                    trace_id=trace_id,
                    detail="Request body too large",
                )
                return

            limited_receive = self._wrap_receive_with_limit(receive)

            async def send_wrapper(message: Message) -> None:
                nonlocal response_started, status_code, route_path
                if message["type"] == "http.response.start":
                    response_started = True
                    status_code = message["status"]
                    headers_raw = list(message.get("headers", []))
                    mutable_headers = MutableHeaders(raw=headers_raw)
                    mutable_headers.append(self._trace_header, trace_id)
                    route = scope.get("route")
                    if route is not None:
                        route_path = getattr(route, "path", route_path) or route_path
                    message = message.copy()
                    message["headers"] = list(mutable_headers.raw)
                await send(message)

            await asyncio.wait_for(
                self.app(scope, limited_receive, send_wrapper),
                timeout=self._timeout_seconds,
            )
        except _BodyTooLargeError:
            status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            if not response_started:
                await self._send_error_response(
                    scope,
                    send,
                    status_code=status_code,
                    trace_id=trace_id,
                    detail="Request body too large",
                )
        except asyncio.TimeoutError:
            status_code = status.HTTP_504_GATEWAY_TIMEOUT
            if not response_started:
                await self._send_error_response(
                    scope,
                    send,
                    status_code=status_code,
                    trace_id=trace_id,
                    detail="Request timed out",
                )
        except Exception:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
            raise
        finally:
            duration = time.perf_counter() - start_time
            if metrics is not None:
                metrics.observe_http_request(
                    method=method,
                    path=route_path,
                    status_code=status_code,
                    duration_seconds=duration,
                )
            reset_trace_id(trace_token)
            reset_current_user_id(user_token)

    def _should_reject_by_header(self, headers: Headers) -> bool:
        content_length = headers.get("content-length")
        if content_length is None:
            return False
        try:
            length = int(content_length)
        except ValueError:
            return False
        return length > self._max_body_bytes >= 0

    def _wrap_receive_with_limit(self, receive: Receive) -> Receive:
        max_bytes = self._max_body_bytes
        bytes_read = 0

        async def limited_receive() -> Message:
            nonlocal bytes_read
            message = await receive()
            if message["type"] != "http.request":
                return message
            body: bytes = message.get("body", b"")
            bytes_read += len(body)
            if bytes_read > max_bytes >= 0:
                raise _BodyTooLargeError
            return message

        return limited_receive

    def _select_trace_id(self, header_value: str | None) -> str:
        if header_value:
            normalized = header_value.strip()
            if normalized:
                return normalized[:128]
        return uuid.uuid4().hex

    async def _send_error_response(
        self,
        scope: Scope,
        send: Send,
        *,
        status_code: int,
        trace_id: str,
        detail: str,
    ) -> None:
        code = self._error_code_for_status(status_code)
        details: dict[str, int] | dict[str, str] = {}
        if status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
            details = {"limit": self._max_body_bytes}
        payload = json.dumps(
            {
                "code": code,
                "error_code": code,
                "message": detail,
                "details": details,
                "trace_id": trace_id,
                "request_id": trace_id,
            }
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(payload)).encode("latin-1")),
            (self._trace_header.encode("latin-1"), trace_id.encode("latin-1")),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": headers,
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
                "more_body": False,
            }
        )

    @staticmethod
    def _error_code_for_status(status_code: int) -> str:
        if status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
            return "payload_too_large"
        if status_code == status.HTTP_504_GATEWAY_TIMEOUT:
            return "request_timeout"
        if status.HTTP_400_BAD_REQUEST <= status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
            return f"http_{status_code}"
        return "internal"

    @staticmethod
    def _store_trace_in_scope(scope: Scope, trace_id: str) -> None:
        state = scope.setdefault("state", {})
        if isinstance(state, dict):
            state["trace_id"] = trace_id
        else:
            setattr(state, "trace_id", trace_id)


__all__ = ["ObservabilityMiddleware"]
