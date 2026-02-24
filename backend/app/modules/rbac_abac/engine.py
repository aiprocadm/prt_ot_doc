from __future__ import annotations

from app.core.rbac_abac import ActorContext, policy_engine

from .types import Decision, PolicyContext, Resource, Subject


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


def authorize(subject: Subject, action: str, resource: Resource, context: PolicyContext | None = None) -> Decision:
    actor = _to_actor(subject)
    ctx = dict(resource.attrs)
    if context and context.tenant_id:
        ctx.setdefault("tenant_id", context.tenant_id)
    result = policy_engine.authorize(actor=actor, action=action, resource=resource.resource_type, ctx=ctx)
    audit_fields: dict[str, object] = {"requested_action": action, "resource": resource.resource_type}
    for key, values in (
        ("company_id", subject.company_ids),
        ("site_id", subject.site_ids),
        ("project_id", subject.project_ids),
        ("contractor_id", subject.contractor_ids),
    ):
        if values:
            audit_fields[key] = list(values)
    if subject.permissions:
        normalized_permission = f"{resource.resource_type}:{action}".lower()
        explicit_permissions = {p.replace(".", ":") for p in subject.permissions}
        if normalized_permission not in explicit_permissions:
            return Decision(
                allow=False,
                reason="missing_permission",
                audit_fields={**audit_fields, "permission": normalized_permission},
            )
    return Decision(allow=result.allowed, reason=result.reason, audit_fields={**audit_fields, **result.audit_meta})
