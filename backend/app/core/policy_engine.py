"""Unified RBAC+ABAC policy engine facade for domain actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.models import RoleEnum, User


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    conditions: tuple[str, ...] = ()
    reason: str | None = None


class PolicyEngine:
    """Small policy adapter used by route/services to standardize access checks."""

    _READ_ROLES = {
        RoleEnum.OWNER,
        RoleEnum.ADMIN,
        RoleEnum.OT_PB_LEAD,
        RoleEnum.OT_SPECIALIST,
        RoleEnum.LINE_MANAGER,
    }
    _WRITE_ROLES = {RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.OT_PB_LEAD}

    def evaluate(
        self,
        user: User,
        action: str,
        resource: str,
        attrs: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        attrs = attrs or {}
        role = user.role

        if action.startswith("read:"):
            if role in self._READ_ROLES:
                return PolicyDecision(allowed=True, conditions=("tenant_scope",))
            return PolicyDecision(False, reason="role_read_denied")

        if action.startswith("write:"):
            if role not in self._WRITE_ROLES:
                return PolicyDecision(False, reason="role_write_denied")
            resource_company_id = attrs.get("resource_company_id")
            if resource_company_id and user.company_id and resource_company_id != user.company_id:
                return PolicyDecision(False, reason="company_scope_denied")
            return PolicyDecision(allowed=True, conditions=("tenant_scope", "company_scope"))

        return PolicyDecision(False, reason=f"unsupported_action:{resource}:{action}")


policy_engine = PolicyEngine()

__all__ = ["PolicyDecision", "PolicyEngine", "policy_engine"]
