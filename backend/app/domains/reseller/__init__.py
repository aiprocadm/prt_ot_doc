"""Reseller bounded context (BIZ-52 срез-1, разд. 52)."""

from app.domains.reseller.hierarchy import (
    RESELLER_KIND,
    CreationPlan,
    HierarchyViolation,
    TenantLevel,
    TenantNode,
    inherited_parent_for_spawned_tenant,
    plan_tenant_creation,
    resolve_level,
    validate_parent_candidate,
)
from app.domains.reseller.scope import FleetScope, is_in_scope, resolve_fleet_scope

__all__ = [
    "RESELLER_KIND",
    "CreationPlan",
    "FleetScope",
    "HierarchyViolation",
    "TenantLevel",
    "TenantNode",
    "inherited_parent_for_spawned_tenant",
    "is_in_scope",
    "plan_tenant_creation",
    "resolve_fleet_scope",
    "resolve_level",
    "validate_parent_candidate",
]
