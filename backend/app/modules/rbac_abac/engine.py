from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.rbac_abac import ActorContext, policy_engine
from app.models.models import AuthzPolicy

from .permission_codes import ROLE_MODULE_DEFAULTS
from .types import Decision, PolicyContext, Resource, Subject

_POLICY_CACHE: dict[str, tuple[datetime, tuple[AuthzPolicy, ...]]] = {}


def _to_actor(subject: Subject) -> ActorContext:
    return ActorContext(
        user_id=subject.user_id,
        tenant_id=subject.tenant_id,
        roles=subject.roles,
        company_ids=subject.company_ids,
        site_ids=subject.site_ids,
        project_ids=subject.project_ids,
        contractor_ids=subject.contractor_ids,
        max_risk_level=subject.risk_level_max,
    )


def _read_attr(path: str, attrs: dict[str, Any], scope: dict[str, Any]) -> Any:
    if path.startswith("$scope."):
        return scope.get(path.removeprefix("$scope."))
    return attrs.get(path)


def _op_eval(*, op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "in":
        return left in (right or [])
    if op == "not_in":
        return left not in (right or [])
    if op == "lt":
        return left is not None and right is not None and left < right
    if op == "lte":
        return left is not None and right is not None and left <= right
    if op == "gt":
        return left is not None and right is not None and left > right
    if op == "gte":
        return left is not None and right is not None and left >= right
    if op == "contains":
        if isinstance(left, (list, tuple, set)):
            return right in left
        if isinstance(right, (list, tuple, set)):
            return left in right
        return False
    if op == "exists":
        return left is not None
    if op == "not_exists":
        return left is None
    return False


def _match_condition(cond: dict[str, Any], attrs: dict[str, Any], scope: dict[str, Any]) -> bool:
    attr = str(cond.get("attr") or "")
    op = str(cond.get("op") or "eq")
    left = _read_attr(attr, attrs, scope)
    raw = cond.get("value")
    right = (
        _read_attr(raw, attrs, scope) if isinstance(raw, str) and raw.startswith("$scope.") else raw
    )
    return _op_eval(op=op, left=left, right=right)


def _match_policy_conditions(
    conditions: dict[str, Any], attrs: dict[str, Any], scope: dict[str, Any]
) -> bool:
    all_conditions = conditions.get("all") or []
    any_conditions = conditions.get("any") or []
    all_ok = all(_match_condition(cond, attrs, scope) for cond in all_conditions)
    if any_conditions:
        return all_ok and any(_match_condition(cond, attrs, scope) for cond in any_conditions)
    return all_ok


def check_module_access(subject: Subject, module_name: str) -> tuple[bool, str]:
    """Check if subject has access to a specific module.

    Returns: (allowed: bool, reason: str)
    """
    first_role = subject.roles[0] if subject.roles else "default"
    # RoleEnum is ``(str, Enum)``; on Python 3.11+ ``str(member)`` yields
    # "RoleEnum.OWNER", not the value. Use ``.value`` for enum members and
    # fall back to the raw string for plain-string roles.
    normalized_role = str(getattr(first_role, "value", first_role)).lower()
    allowed_modules = ROLE_MODULE_DEFAULTS.get(normalized_role, [])

    if module_name in allowed_modules:
        return True, "module_allowed"
    return False, "module_denied"


def _get_cached_policies(ctx: PolicyContext) -> tuple[AuthzPolicy, ...]:
    provided = (ctx.request_attrs or {}).get("policies")
    if isinstance(provided, (list, tuple)):
        # Explicit injection seam (overrides / tests): trust duck-typed policy
        # objects that expose the fields the matcher needs, rather than requiring
        # the SQLAlchemy ``AuthzPolicy`` type. The DB branch below still yields
        # real ``AuthzPolicy`` rows, so production behaviour is unchanged.
        return tuple(
            item
            for item in provided
            if hasattr(item, "resource") and hasattr(item, "action") and hasattr(item, "effect")
        )
    session = (ctx.request_attrs or {}).get("db_session")
    if session is None or not ctx.tenant_id:
        return ()
    updated_at = (ctx.request_attrs or {}).get("policies_updated_at")
    ts = updated_at if isinstance(updated_at, datetime) else datetime.now(tz=timezone.utc)
    cached = _POLICY_CACHE.get(ctx.tenant_id)
    if cached and cached[0] >= ts:
        return cached[1]
    return ()


def evaluate(
    subject: Subject, action: str, resource: Resource, context: PolicyContext | None = None
) -> Decision:
    actor = _to_actor(subject)
    ctx = dict(resource.attrs)
    if context:
        ctx.update(context.request_attrs or {})
    if context and context.tenant_id:
        ctx.setdefault("tenant_id", context.tenant_id)

    # NOTE: Module-level gating is intentionally NOT enforced here. ``evaluate``
    # is the ABAC policy engine: access can be granted by explicit permissions or
    # tenant ABAC allow-policies, which a hardcoded role→module table must not
    # short-circuit. Coarse module gating lives in ``app.core.rbac_abac``
    # (System B, ``policy_engine.can``); ``check_module_access`` /
    # ``ROLE_MODULE_DEFAULTS`` here are for UI-navigation filtering.

    # RBAC precondition
    normalized_permission = f"{resource.resource_type}:{action}".lower()
    explicit_permissions = {p.replace(".", ":") for p in subject.permissions}
    if {str(role).lower() for role in subject.roles} & {"owner", "admin"}:
        explicit_permissions.add(normalized_permission)
    if normalized_permission not in explicit_permissions:
        return Decision(
            allow=False,
            reason="missing_permission",
            audit_fields={"permission": normalized_permission},
        )

    # fallback static policy engine (deny-by-default)
    result = policy_engine.authorize(
        actor=actor, action=action, resource=resource.resource_type, ctx=ctx
    )

    # ABAC dynamic policies (best-effort; deny override)
    matched_policy_id: str | None = None
    if context:
        rules = _get_cached_policies(context)
        applicable = [
            rule
            for rule in rules
            if rule.enabled and rule.resource == resource.resource_type and rule.action == action
        ]
        applicable.sort(key=lambda item: item.priority)
        matched: list[AuthzPolicy] = [
            rule
            for rule in applicable
            if _match_policy_conditions(rule.conditions_json or {}, ctx, context.abac_scopes or {})
        ]
        if matched:
            top_priority = matched[0].priority
            top = [item for item in matched if item.priority == top_priority]
            deny_rule = next((item for item in top if (item.effect or "").lower() == "deny"), None)
            if deny_rule is not None:
                return Decision(allow=False, reason="policy_deny", matched_policy_id=deny_rule.id)
            allow_rule = next(
                (item for item in top if (item.effect or "").lower() == "allow"), None
            )
            if allow_rule is not None:
                return Decision(allow=True, reason="policy_allow", matched_policy_id=allow_rule.id)

    return Decision(
        allow=result.allowed,
        reason=result.reason,
        matched_policy_id=matched_policy_id,
        audit_fields={
            "resource": resource.resource_type,
            "requested_action": action,
            **result.audit_meta,
        },
    )


def authorize(
    subject: Subject, action: str, resource: Resource, context: PolicyContext | None = None
) -> Decision:
    return evaluate(subject, action, resource, context)
