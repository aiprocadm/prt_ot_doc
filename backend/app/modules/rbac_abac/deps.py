from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.rbac_abac import ROLE_ALIASES, permissions_for_role
from app.services.audit import AuditService

from .engine import evaluate
from .types import PolicyContext, Resource, Subject


def _subject_from_request(request: Request) -> Subject:
    claims = getattr(request.state, "claims", {}) or {}

    raw_roles = [str(role).lower() for role in claims.get("roles", []) if role]
    single_role = claims.get("role")
    if isinstance(single_role, str) and single_role:
        raw_roles.append(single_role.lower())

    normalized_roles = tuple(dict.fromkeys(ROLE_ALIASES.get(role, role) for role in raw_roles))

    raw_permissions = [
        str(permission).lower() for permission in claims.get("permissions", []) if permission
    ]
    if raw_permissions:
        permissions = tuple(dict.fromkeys(raw_permissions))
    else:
        # Срез-227: токен прав в себе не несёт, и раньше здесь подставлялся
        # словарь, в котором семи настоящих ролей нет вовсе — предусловие
        # движка отказывало им всем. Теперь права берутся из единой карты.
        permissions = tuple(
            dict.fromkeys(
                permission
                for role in normalized_roles
                for permission in sorted(permissions_for_role(role))
            )
        )

    return Subject(
        user_id=claims.get("sub"),
        tenant_id=claims.get("tenant_id") or claims.get("tenant"),
        roles=normalized_roles,
        permissions=permissions,
        company_ids=tuple(str(item) for item in claims.get("company_ids", []) if item),
        site_ids=tuple(str(item) for item in claims.get("site_ids", []) if item),
        project_ids=tuple(str(item) for item in claims.get("project_ids", []) if item),
        contractor_ids=tuple(str(item) for item in claims.get("contractor_ids", []) if item),
        risk_level_max=claims.get("max_risk_level"),
    )


def require_action(
    resource_type: str,
    action: str,
    *,
    resource_attrs_getter: Callable[[Request], dict[str, Any]] | None = None,
) -> Callable[[Request], Any]:
    async def dependency(request: Request) -> None:
        subject = _subject_from_request(request)
        resource_attrs = resource_attrs_getter(request) if resource_attrs_getter else {}
        decision = evaluate(
            subject,
            action=action,
            resource=Resource(resource_type=resource_type, attrs=resource_attrs),
            context=PolicyContext(
                tenant_id=subject.tenant_id,
                user_id=subject.user_id,
                roles=subject.roles,
                permissions=subject.permissions,
                abac_scopes={
                    "company_ids": list(subject.company_ids),
                    "site_ids": list(subject.site_ids),
                    "project_ids": list(subject.project_ids),
                    "contractor_ids": list(subject.contractor_ids),
                    "risk_level_max": subject.risk_level_max,
                },
                request_attrs={
                    "path": request.url.path,
                    "method": request.method,
                },
                action=action,
                resource=resource_type,
                correlation_id=getattr(request.state, "correlation_id", None)
                or getattr(request.state, "trace_id", None),
            ),
        )
        if not decision.allow:
            session = getattr(request.state, "db_session", None)
            if session is not None:
                audit = AuditService(session)
                await audit.log_event(
                    tenant_id=subject.tenant_id or "-",
                    action="access_deny",
                    object_type=resource_type,
                    object_id=str(
                        resource_attrs.get("id") or resource_attrs.get("resource_id") or "-"
                    ),
                    user_id=subject.user_id,
                    ip=request.client.host if request.client else "unknown",
                    details={
                        "reason": decision.reason,
                        "correlation_id": getattr(request.state, "correlation_id", None)
                        or getattr(request.state, "trace_id", None),
                        "matched_policy_id": decision.matched_policy_id,
                        "audit_fields": decision.audit_fields,
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "AUTHZ_DENIED",
                    "type": "authorization",
                    "message": "Access denied by policy",
                    "correlation-id": getattr(request.state, "correlation_id", None)
                    or getattr(request.state, "trace_id", None),
                },
            )

    return dependency


def require_permission(permission_code: str) -> Callable[[Request], Any]:
    normalized = permission_code.replace(".", ":").lower()
    resource_type, _, action = normalized.partition(":")
    if not action:
        resource_type, _, action = normalized.partition("/")
    normalized_action = action or "read"
    return require_action(resource_type=resource_type, action=normalized_action)


def require_access(
    resource: str,
    action: str,
    *,
    resource_attrs_getter: Callable[[Request], dict[str, Any]] | None = None,
) -> Callable[[Request], Any]:
    return require_action(
        resource_type=resource, action=action, resource_attrs_getter=resource_attrs_getter
    )
