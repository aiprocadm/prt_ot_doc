"""FastAPI middleware for tenant extraction."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.security import verify_token
from app.core.tenant import TENANT_HEADER_ALIASES, tenant_required
from app.db.session import AsyncSessionLocal
from app.models.models import Tenant, TenantQuota


class TenantMiddleware(BaseHTTPMiddleware):
    """Populate tenant context from request headers and guard system routes."""

    def __init__(self, app: ASGIApp, *, metrics_enabled: bool = False) -> None:
        super().__init__(app)
        self._metrics_enabled = metrics_enabled
        self._system_paths = {"/health", "/ready", "/healthz", "/readyz"}
        self._public_prefixes = ("/api/v1/auth", "/api/v1/public")

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            UUID(str(value))
        except (ValueError, TypeError):
            return False
        return True

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path

        if path == "/metrics" and not self._metrics_enabled:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        if (
            path in self._system_paths
            or (self._metrics_enabled and path == "/metrics")
            or path.startswith("/docs")
            or path == "/openapi.json"
            or any(path.startswith(prefix) for prefix in self._public_prefixes)
        ):
            return await call_next(request)

        header_slug = None
        for header_name in TENANT_HEADER_ALIASES:
            header_slug = request.headers.get(header_name)
            if header_slug:
                break
        if path.startswith("/api/v1/") and not header_slug:
            correlation_id = getattr(request.state, "trace_id", "")
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "missing_tenant",
                    "type": "tenancy",
                    "message": "X-Tenant required",
                    "correlation-id": correlation_id,
                },
            )
        if not header_slug:
            tenant_required(None)
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

        info = tenant_required(normalized_header)
        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
            identifier = info.slug
            filters = [Tenant.slug == identifier, Tenant.code == identifier]
            if self._is_uuid(identifier):
                filters.append(Tenant.id == identifier)
            tenant = (await session.execute(select(Tenant).where(or_(*filters)))).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail={"code": "tenant_not_found", "type": "validation", "message": "Tenant not found"},
            )
        if token_slug:
            token_scope = token_slug.casefold()
            tenant_scopes = {
                (tenant.slug or "").casefold(),
                (tenant.code or "").casefold(),
                str(tenant.id).casefold(),
            }
            if token_scope not in tenant_scopes:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Tenant header does not match token scope",
                )
        if not tenant.is_active:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "tenant_inactive", "type": "validation", "message": "Tenant inactive"},
            )
        request.state.tenant_id = str(tenant.id)
        request.state.tenant_slug = tenant.slug
        request.state.tenant_schema = tenant.schema_name or f"tenant_{tenant.slug}"
        request.state.tenant_code = tenant.code
        request.state.tenant_record = tenant
        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
            quota = (
                await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
            ).scalar_one_or_none()
        request.state.tenant_quota = quota
        return await call_next(request)
