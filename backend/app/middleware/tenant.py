"""FastAPI middleware for tenant extraction and context propagation."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.security import verify_token
from app.core.tenant import TENANT_HEADER, TENANT_HEADER_ALIASES, tenant_required
from app.db.session import AsyncSessionLocal
from app.modules.tenancy.context import TenantContext, reset_tenant_context, set_tenant_context
from app.models.models import Tenant, TenantQuota, TenantSettings


class TenantMiddleware(BaseHTTPMiddleware):
    """Populate tenant context from request headers and guard system routes."""

    def __init__(self, app: ASGIApp, *, metrics_enabled: bool = False) -> None:
        super().__init__(app)
        self._metrics_enabled = metrics_enabled
        self._system_paths = {"/health", "/ready", "/healthz", "/readyz"}
        self._public_prefixes = ("/api/v1/auth", "/api/v1/public", "/api/v1/webhooks/incoming")

    @staticmethod
    def _is_uuid(value: str) -> bool:
        try:
            UUID(str(value))
        except (ValueError, TypeError):
            return False
        return True

    @staticmethod
    def _error(status_code: int, correlation_id: str, *, code: str, message: str, err_type: str = "tenancy") -> HTTPException:
        return HTTPException(
            status_code,
            detail={
                "code": code,
                "type": err_type,
                "message": message,
                "correlation_id": correlation_id,
            },
        )

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        path = request.url.path

        if path == "/metrics" and not self._metrics_enabled:
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        if (
            path in self._system_paths
            or (self._metrics_enabled and path == "/metrics")
            or path.startswith("/docs")
            or path.endswith("/openapi.json")
            or any(path.startswith(prefix) for prefix in self._public_prefixes)
        ):
            return await call_next(request)

        correlation_id = request.headers.get("x-correlation-id") or getattr(request.state, "trace_id", None) or str(uuid4())
        request.state.correlation_id = correlation_id

        header_slug = None
        for header_name in TENANT_HEADER_ALIASES:
            header_slug = request.headers.get(header_name)
            if header_slug:
                break
        if path.startswith("/api/v1/") and not header_slug:
            raise self._error(status.HTTP_400_BAD_REQUEST, correlation_id, code="TENANT_REQUIRED", message="X-Tenant header required")
        if not header_slug:
            tenant_required(None)
        token_slug: str | None = None
        token_claims: dict[str, object] = {}
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(None, 1)[1].strip()
            if token:
                try:
                    payload = verify_token(token, expected_type="access")
                    token_claims = payload
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
            raise self._error(
                status.HTTP_404_NOT_FOUND,
                correlation_id,
                code="TENANT_NOT_FOUND",
                message="Tenant not found",
            )
        if token_slug and token_slug.casefold() not in {str(tenant.id).casefold(), str(tenant.slug).casefold(), str(tenant.code).casefold()}:
            raise self._error(
                status.HTTP_403_FORBIDDEN,
                correlation_id,
                code="TENANT_SCOPE_MISMATCH",
                message="Tenant header does not match token scope",
            )
        if not tenant.is_active:
            raise self._error(
                status.HTTP_403_FORBIDDEN,
                correlation_id,
                code="TENANT_BLOCKED",
                message="Tenant blocked",
            )
        request.state.tenant_id = str(tenant.id)
        request.state.tenant_slug = tenant.slug
        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
            settings = (
                await session.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
            ).scalar_one_or_none()
            quota = (
                await session.execute(select(TenantQuota).where(TenantQuota.tenant_id == tenant.id))
            ).scalar_one_or_none()
        request.state.tenant_schema = (settings.schema_name if settings else None) or tenant.schema_name or f"tenant_{tenant.slug}"
        request.state.tenant_s3_prefix = (settings.s3_prefix if settings else None) or tenant.s3_prefix or str(tenant.id)
        request.state.tenant_code = tenant.code
        request.state.tenant_record = tenant
        request.state.tenant_settings = settings
        request.state.tenant_quota = quota

        roles_raw = request.headers.get("x-roles", "")
        attrs_raw = request.headers.get("x-attributes", "")
        attributes: dict[str, str] = {}
        for chunk in attrs_raw.split(","):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            attributes[k.strip()] = v.strip()
        ctx = TenantContext(
            tenant_id=str(tenant.id),
            slug=tenant.slug,
            schema=request.state.tenant_schema,
            s3_prefix=request.state.tenant_s3_prefix,
            tenant_level=getattr(tenant, "kind", "customer"),
            plan=((getattr(tenant, "settings", None) or {}).get("plan") if isinstance(getattr(tenant, "settings", None), dict) else None) or "Free",
            limits={
                "users": None,
                "templates": None,
                "generations_per_month": quota.max_doc_generations_per_month if quota else None,
                "s3_gb": int((quota.max_storage_mb or 0) / 1024) if quota else None,
                "edo_out_docs": quota.monthly_edo_outgoing if quota else None,
                "enforce_billing_gate": quota.enforce_billing_gate if quota else False,
            },
            max_parallel_jobs=(quota.max_parallel_jobs if quota else None),
            max_storage_mb=(quota.max_storage_mb if quota else None),
            max_generations_per_month=(quota.max_doc_generations_per_month if quota else None),
            correlation_id=correlation_id,
            actor_id=request.headers.get("x-actor-id"),
            roles=tuple([r.strip() for r in roles_raw.split(",") if r.strip()]),
            attributes=attributes or None,
        )
        request.state.claims = token_claims
        request.state.user_id = token_claims.get("sub") if token_claims else request.headers.get("x-actor-id")
        request.state.roles = tuple(str(role).lower() for role in token_claims.get("roles", [])) if token_claims else tuple()
        request.state.scopes = {
            "company_ids": list(token_claims.get("company_ids", [])) if token_claims else [],
            "site_ids": list(token_claims.get("site_ids", [])) if token_claims else [],
            "project_ids": list(token_claims.get("project_ids", [])) if token_claims else [],
            "contractor_ids": list(token_claims.get("contractor_ids", [])) if token_claims else [],
        }
        request.state.tenant_context = ctx
        token = set_tenant_context(ctx)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-Id"] = correlation_id
            return response
        finally:
            reset_tenant_context(token)


__all__ = ["TENANT_HEADER", "TenantMiddleware"]
