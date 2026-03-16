from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.services.audit import AuditService
from fastapi import HTTPException, Request, status
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


class Action(str, enum.Enum):
    READ = "read"
    LIST = "list"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    SIGN = "sign"
    SEND_EDO = "send_edo"
    EXPORT = "export"
    DOWNLOAD = "download"
    RUN_PIPELINE = "run_pipeline"
    RETRY_JOB = "retry_job"
    CANCEL_JOB = "cancel_job"


ROLE_ALIASES: dict[str, str] = {
    "tenant_owner": "owner",
    "tenant_admin": "admin",
    "teacher": "instructor",
    "hsse_head": "hse_head",
    "hsse_specialist": "hse_specialist",
    "contractor_inspector": "inspector_contractor",
    "methodist_legal": "methodist",
}


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: str | None
    tenant_id: str | None
    roles: tuple[str, ...]
    company_ids: tuple[str, ...] = ()
    site_ids: tuple[str, ...] = ()
    project_ids: tuple[str, ...] = ()
    contractor_ids: tuple[str, ...] = ()
    allowed_statuses: tuple[str, ...] = ()
    max_risk_level: int | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    reason: str
    matched_roles: tuple[str, ...] = ()
    matched_rules: tuple[str, ...] = ()
    audit_meta: dict[str, Any] = field(default_factory=dict)


def _normalize_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item)
    return ()


def _normalize_risk_level(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    mapping = {"low": 1, "medium": 2, "high": 3, "critical": 4, "crit": 4}
    if normalized in mapping:
        return mapping[normalized]
    try:
        return int(normalized)
    except ValueError:
        return None


def _normalize_role(role: str) -> str:
    normalized = str(role).lower()
    return ROLE_ALIASES.get(normalized, normalized)


def actor_from_claims(claims: dict[str, Any] | Any, roles: list[str]) -> ActorContext:
    return ActorContext(
        user_id=str(claims.get("sub") or claims.get("user_id") or "") or None,
        tenant_id=str(claims.get("tenant_id") or claims.get("tenant") or "") or None,
        roles=tuple(_normalize_role(role) for role in roles),
        company_ids=_normalize_list(claims.get("company_ids") or claims.get("company_id")),
        site_ids=_normalize_list(claims.get("site_ids") or claims.get("site_id")),
        project_ids=_normalize_list(claims.get("project_ids") or claims.get("project_id")),
        contractor_ids=_normalize_list(claims.get("contractor_ids") or claims.get("contractor_id")),
        allowed_statuses=_normalize_list(claims.get("allowed_statuses") or claims.get("statuses")),
        max_risk_level=_normalize_risk_level(claims.get("max_risk_level")),
    )


RESOURCE_PERMISSIONS: dict[str, set[str]] = {
    "templates": {"read", "list", "create", "update", "delete", "approve"},
    "template_versions": {"read", "list", "create", "update", "delete", "approve"},
    "documents": {
        "read",
        "list",
        "create",
        "update",
        "delete",
        "approve",
        "sign",
        "send_edo",
        "export",
        "download",
        "run_pipeline",
    },
    "document_versions": {"read", "list", "create", "update", "delete", "download"},
    "document_jobs": {"read", "list", "run_pipeline", "retry_job", "cancel_job"},
    "files": {"read", "list", "create", "delete", "download", "sign"},
    "package_presets": {"read", "list", "create", "update", "delete"},
    "package_profiles": {"read", "list", "create", "update", "delete"},
    "risk_maps": {"read", "list", "create", "update", "delete", "approve", "export"},
    "risk_methodologies": {"read", "list", "create", "update", "delete"},
    "ppe_norms": {"read", "list", "create", "update", "delete"},
    "ppe_issues": {"read", "list", "create", "update", "delete"},
    "warehouse_stock": {"read", "list", "create", "update", "delete"},
    "trainings": {"read", "list", "create", "update", "delete", "approve"},
    "briefings": {"read", "list", "create", "update", "delete"},
    "incidents": {"read", "list", "create", "update", "delete", "approve", "export"},
    "inspections": {"read", "list", "create", "update", "delete", "approve", "export"},
    "reports": {"read", "list", "export", "download"},
    "admin": {"read", "list", "create", "update", "delete"},
}

_ROLE_FULL = {
    f"{resource}:{action}"
    for resource, actions in RESOURCE_PERMISSIONS.items()
    for action in actions
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": _ROLE_FULL,
    "admin": _ROLE_FULL,
    "methodist": {
        "templates:read",
        "templates:list",
        "templates:create",
        "templates:update",
        "templates:delete",
        "templates:approve",
        "template_versions:read",
        "template_versions:list",
        "template_versions:create",
        "template_versions:update",
        "template_versions:approve",
    },
    "lawyer": {"documents:read", "documents:list", "templates:read", "templates:list"},
    "project_manager": {
        "documents:read",
        "documents:list",
        "documents:create",
        "documents:update",
        "document_jobs:run_pipeline",
        "document_jobs:retry_job",
        "reports:read",
        "reports:list",
    },
    "executor": {
        "documents:read",
        "documents:list",
        "documents:update",
        "files:read",
        "files:download",
    },
    "clerk": {
        "documents:read",
        "documents:list",
        "documents:update",
        "documents:send_edo",
        "files:read",
        "files:download",
    },
    "instructor": {
        "trainings:read",
        "trainings:list",
        "trainings:create",
        "trainings:update",
        "trainings:delete",
        "briefings:read",
        "briefings:list",
        "briefings:create",
        "briefings:update",
    },
    "student": {"trainings:read", "trainings:list"},
    "hse_head": {
        "documents:read",
        "documents:list",
        "documents:create",
        "documents:update",
        "risk_maps:read",
        "risk_maps:list",
        "risk_maps:create",
        "risk_maps:update",
        "ppe_norms:read",
        "ppe_norms:list",
        "ppe_norms:create",
        "ppe_norms:update",
        "inspections:read",
        "inspections:list",
        "inspections:create",
        "inspections:update",
        "incidents:read",
        "incidents:list",
        "incidents:create",
        "incidents:update",
    },
    "hse_specialist": {
        "documents:read",
        "documents:list",
        "documents:create",
        "documents:update",
        "risk_maps:read",
        "risk_maps:list",
        "risk_maps:create",
        "risk_maps:update",
        "ppe_norms:read",
        "ppe_norms:list",
        "ppe_norms:create",
        "ppe_norms:update",
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
    },
    "fire_engineer": {
        "documents:read",
        "documents:list",
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
    },
    "ecologist": {
        "documents:read",
        "documents:list",
        "risk_maps:read",
        "risk_maps:list",
        "incidents:read",
        "incidents:list",
    },
    "hr": {
        "documents:read",
        "documents:list",
        "trainings:read",
        "trainings:list",
        "trainings:create",
        "trainings:update",
    },
    "accountant": {"reports:read", "reports:list", "reports:export"},
    "line_manager": {
        "documents:read",
        "documents:list",
        "documents:update",
        "incidents:read",
        "inspections:read",
        "inspections:list",
    },
    "client": {
        "documents:read",
        "documents:list",
        "documents:download",
        "reports:read",
        "reports:list",
    },
    "auditor_ro": {
        "documents:read",
        "documents:list",
        "risk_maps:read",
        "risk_maps:list",
        "ppe_norms:read",
        "ppe_norms:list",
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
        "reports:read",
        "reports:list",
    },
    "inspector_contractor": {
        "inspections:read",
        "inspections:list",
        "incidents:read",
        "incidents:list",
    },
}

SCOPED_RESOURCES = {
    "templates",
    "template_versions",
    "documents",
    "document_versions",
    "document_jobs",
    "files",
    "risk_maps",
    "risk_methodologies",
    "ppe_norms",
    "ppe_issues",
    "warehouse_stock",
    "trainings",
    "briefings",
    "incidents",
    "inspections",
    "reports",
}


class PolicyEngine:
    _ACTION_ALIASES = {
        "generate": "run_pipeline",
        "run": "run_pipeline",
        "cancel": "cancel_job",
    }

    def enforce(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        """Unified policy entrypoint required by business guards."""

        return self.can(actor=actor, action=action, resource=resource, obj=obj, ctx=ctx)

    def can(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        normalized_action = self._ACTION_ALIASES.get(action.lower(), action.lower())
        normalized_resource = resource.lower()
        permission_code = f"{normalized_resource}:{normalized_action}"

        matched_roles = tuple(
            role for role in actor.roles if permission_code in ROLE_PERMISSIONS.get(role, set())
        )
        if not matched_roles:
            return Decision(False, "missing_permission", audit_meta={"permission": permission_code})

        if "auditor_ro" in actor.roles and normalized_action not in {"read", "list"}:
            return Decision(False, "auditor_read_only", matched_roles=matched_roles)

        if {"owner", "admin"}.intersection(actor.roles):
            return Decision(
                True,
                "explicit_allow",
                matched_roles=matched_roles,
                matched_rules=("rbac", "admin_bypass"),
            )

        if not self._scope_check(actor=actor, obj=obj, ctx=ctx or {}):
            return Decision(
                False, "scope_mismatch", matched_roles=matched_roles, matched_rules=("scope_check",)
            )

        return Decision(
            True, "explicit_allow", matched_roles=matched_roles, matched_rules=("rbac", "abac")
        )

    def authorize(
        self,
        actor: ActorContext,
        action: str,
        resource: str,
        obj: Any | None = None,
        ctx: dict[str, Any] | None = None,
    ) -> Decision:
        return self.can(actor=actor, action=action, resource=resource, obj=obj, ctx=ctx)

    @staticmethod
    def _scope_check(*, actor: ActorContext, obj: Any | None, ctx: dict[str, Any]) -> bool:
        attrs: dict[str, Any] = dict(ctx)
        if obj is not None:
            for name in (
                "company_id",
                "site_id",
                "project_id",
                "contractor_id",
                "document_id",
                "status",
                "risk_level",
            ):
                if hasattr(obj, name):
                    attrs.setdefault(name, getattr(obj, name))

        checks = (
            ("company_id", actor.company_ids),
            ("site_id", actor.site_ids),
            ("project_id", actor.project_ids),
            ("contractor_id", actor.contractor_ids),
        )
        for key, allowed_values in checks:
            value = attrs.get(key)
            if value and allowed_values and str(value) not in set(map(str, allowed_values)):
                return False

        status_value = attrs.get("status")
        if (
            status_value
            and actor.allowed_statuses
            and str(status_value) not in set(actor.allowed_statuses)
        ):
            return False

        risk_level = _normalize_risk_level(attrs.get("risk_level"))
        if (
            risk_level is not None
            and actor.max_risk_level is not None
            and risk_level > actor.max_risk_level
        ):
            return False

        return True


policy_engine = PolicyEngine()


def policy_forbidden(reason: str, *, correlation_id: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "forbidden",
            "type": "policy",
            "message": "forbidden",
            "reason_code": reason,
            "correlation-id": correlation_id,
        },
    )


def apply_abac_filters(query: Select[Any], actor: ActorContext, model: type[Any]) -> Select[Any]:
    return scoped_query(query, model=model, actor=actor, resource=model.__tablename__)


def scoped_query(
    query: Select[Any], *, model: type[Any], actor: ActorContext, resource: str | None = None
) -> Select[Any]:
    filters = []
    scoped_fields = 0
    normalized_resource = (resource or getattr(model, "__tablename__", "") or "").lower()

    if hasattr(model, "company_id"):
        scoped_fields += 1
        if actor.company_ids:
            filters.append(model.company_id.in_(actor.company_ids))
    elif normalized_resource in {"company", "companies"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.company_ids:
            filters.append(model.id.in_(actor.company_ids))
    if hasattr(model, "site_id"):
        scoped_fields += 1
        if actor.site_ids:
            filters.append(model.site_id.in_(actor.site_ids))
    elif normalized_resource in {"site", "sites"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.site_ids:
            filters.append(model.id.in_(actor.site_ids))
    if hasattr(model, "project_id"):
        scoped_fields += 1
        if actor.project_ids:
            filters.append(model.project_id.in_(actor.project_ids))
    elif normalized_resource in {"project", "projects"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.project_ids:
            filters.append(model.id.in_(actor.project_ids))
    if hasattr(model, "contractor_id"):
        scoped_fields += 1
        if actor.contractor_ids:
            filters.append(model.contractor_id.in_(actor.contractor_ids))
    elif normalized_resource in {"contractor", "contractors"} and hasattr(model, "id"):
        scoped_fields += 1
        if actor.contractor_ids:
            filters.append(model.id.in_(actor.contractor_ids))
    if hasattr(model, "status") and actor.allowed_statuses:
        filters.append(model.status.in_(actor.allowed_statuses))
    if hasattr(model, "risk_level") and actor.max_risk_level is not None:
        filters.append(model.risk_level <= actor.max_risk_level)
    if hasattr(model, "deleted_at"):
        filters.append(model.deleted_at.is_(None))
    if filters:
        query = query.where(and_(*filters))

    if (
        scoped_fields == 0
        and normalized_resource in SCOPED_RESOURCES
        and any((actor.company_ids, actor.site_ids, actor.project_ids, actor.contractor_ids))
    ):
        raise policy_forbidden("scoped_resource_without_scope_fields")
    return query


async def audit_authz_decision(
    *,
    session: AsyncSession,
    request: Request,
    actor: ActorContext,
    resource: str,
    action: str,
    decision: Decision,
    object_id: str | None = None,
) -> None:
    tenant = str(
        session.info.get("tenant_id") or session.info.get("tenant") or actor.tenant_id or ""
    )
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=tenant,
        action="authz_decision",
        object_type=resource,
        object_id=object_id or "-",
        user_id=actor.user_id,
        ip=request.client.host if request.client else "unknown",
        details={
            "event_type": "authz_decision",
            "resource": resource,
            "decision_action": action,
            "path": request.url.path,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "matched_roles": list(decision.matched_roles),
            "matched_rules": list(decision.matched_rules),
            "scopes": {
                "company_ids": list(actor.company_ids),
                "site_ids": list(actor.site_ids),
                "project_ids": list(actor.project_ids),
                "contractor_ids": list(actor.contractor_ids),
                "allowed_statuses": list(actor.allowed_statuses),
                "max_risk_level": actor.max_risk_level,
            },
        },
    )
