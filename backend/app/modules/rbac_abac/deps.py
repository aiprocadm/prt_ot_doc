from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from .engine import authorize
from .types import PolicyContext, Resource, Subject


def _subject_from_request(request: Request) -> Subject:
    claims = getattr(request.state, "claims", {}) or {}
    roles = tuple(str(role).lower() for role in claims.get("roles", []))
    return Subject(
        user_id=claims.get("sub"),
        tenant_id=claims.get("tenant_id") or claims.get("tenant"),
        roles=roles,
        company_ids=tuple(str(item) for item in claims.get("company_ids", []) if item),
        site_ids=tuple(str(item) for item in claims.get("site_ids", []) if item),
        project_ids=tuple(str(item) for item in claims.get("project_ids", []) if item),
        contractor_ids=tuple(str(item) for item in claims.get("contractor_ids", []) if item),
    )


def require_action(resource_type: str, action: str) -> Callable[[Request], Any]:
    async def dependency(request: Request) -> None:
        subject = _subject_from_request(request)
        decision = authorize(
            subject,
            action=action,
            resource=Resource(resource_type=resource_type),
            context=PolicyContext(
                tenant_id=subject.tenant_id,
                request_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                correlation_id=getattr(request.state, "trace_id", None),
            ),
        )
        if not decision.allow:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AUTHZ_DENIED",
                    "type": "authorization",
                    "message": "Access denied by policy",
                    "correlation-id": getattr(request.state, "trace_id", None),
                },
            )

    return dependency


def require_permission(permission_code: str) -> Callable[[Request], Any]:
    resource_type, _, action = permission_code.partition(":")
    normalized_action = "read" if action in {"read", "list"} else "update"
    return require_action(resource_type=resource_type, action=normalized_action)
