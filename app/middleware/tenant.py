"""FastAPI middleware for tenant extraction."""
from __future__ import annotations

from fastapi import HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.security import verify_token
from app.core.tenant import TENANT_HEADER, TENANT_HEADER_ALIASES, tenant_required


class TenantMiddleware(BaseHTTPMiddleware):
    """Populate tenant context from request headers and guard system routes."""

    def __init__(self, app: ASGIApp, *, metrics_enabled: bool = False) -> None:
        super().__init__(app)
        self._metrics_enabled = metrics_enabled
        self._system_paths = {"/health", "/ready", "/healthz", "/readyz"}
        self._public_prefixes = ("/api/v1/auth", "/api/v1/public")

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path

        if path == "/metrics" and not self._metrics_enabled:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        if (
            path in self._system_paths
            or (self._metrics_enabled and path == "/metrics")
            or path.startswith("/docs")
            or any(path.startswith(prefix) for prefix in self._public_prefixes)
        ):
            return await call_next(request)

        header_slug = None
        for header_name in TENANT_HEADER_ALIASES:
            header_slug = request.headers.get(header_name)
            if header_slug:
                break
        token_slug: str | None = None
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(None, 1)[1].strip()
            if token:
                try:
                    payload = verify_token(token, expected_type="access")
                except Exception as exc:
                    raise HTTPException(
                        status.HTTP_401_UNAUTHORIZED,
                        "Invalid authentication token",
                    ) from exc
                raw_slug = str(payload.get("tenant") or "").strip()
                token_slug = raw_slug or None

        normalized_header = header_slug.strip() if header_slug else None
        if (
            normalized_header
            and token_slug
            and normalized_header.casefold() != token_slug.casefold()
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Tenant header does not match token scope",
            )

        effective_slug = token_slug or normalized_header
        if not effective_slug:
            tenant_required(None)
        tenant_required(effective_slug)
        return await call_next(request)
