"""Unified RBAC+ABAC policy engine facade for domain actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.rbac_abac import actor_from_claims
from app.core.rbac_abac import policy_engine as rbac_abac_engine
from app.models.models import User


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    conditions: tuple[str, ...] = ()
    reason: str | None = None


class PolicyEngine:
    """Backwards-compatible adapter around the central authz policy engine."""

    def evaluate(
        self,
        user: User,
        action: str,
        resource: str,
        attrs: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        attrs = attrs or {}
        roles = [user.role.value]
        roles.extend(str(role.role.value) for role in getattr(user, "roles", []))
        claims = {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "company_id": user.company_id,
            "site_id": attrs.get("site_id"),
            "project_id": attrs.get("project_id"),
            "contractor_id": attrs.get("contractor_id"),
        }
        actor = actor_from_claims(claims, roles)
        normalized_action = action.split(":", 1)[0].lower()
        if normalized_action == "write":
            normalized_action = "update"
        elif normalized_action not in {
            "read",
            "list",
            "create",
            "update",
            "delete",
            "approve",
            "sign",
            "export",
            "download",
            "run_pipeline",
            "retry_job",
            "cancel_job",
            "send_edo",
        }:
            normalized_action = action.split(":", 1)[-1].lower()
        decision = rbac_abac_engine.authorize(
            actor, action=normalized_action, resource=resource, ctx=attrs
        )
        return PolicyDecision(
            allowed=decision.allowed,
            conditions=decision.matched_rules,
            reason=decision.reason,
        )


policy_engine_adapter = PolicyEngine()
policy_engine = policy_engine_adapter

__all__ = ["PolicyDecision", "PolicyEngine", "policy_engine"]
