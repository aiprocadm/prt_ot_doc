"""Tenant guard helpers for business API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, Request, status

from app.core.tenant import TENANT_HEADER_ALIASES

PUBLIC_PATH_PREFIXES = ("/healthz", "/readyz", "/api/v1/auth")


def is_public_path(path: str) -> bool:
    return path in {"/healthz", "/readyz"} or any(
        path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES
    )


def require_tenant(request: Request) -> str:
    """Validate X-Tenant header and persist tenant id into request.state."""

    raw_value: str | None = None
    for header_name in TENANT_HEADER_ALIASES:
        candidate = request.headers.get(header_name)
        if candidate:
            raw_value = candidate.strip()
            break

    if not raw_value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "TENANT_REQUIRED",
                "type": "tenancy",
                "message": "X-Tenant header required",
                "correlation_id": getattr(request.state, "trace_id", None),
            },
        )

    # Accept slug or UUID; if UUID is passed we preserve it in tenant_id.
    try:
        UUID(raw_value)
        request.state.tenant_id = raw_value
    except ValueError:
        request.state.tenant_slug = raw_value.lower()
    return raw_value
