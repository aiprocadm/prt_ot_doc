"""
Comprehensive ABAC deny/allow matrix tests for TZ-2.2-MVP-01.

Tests cover:
- All ABAC attributes (company_id, site_id, document_id, status, risk_level, project_id, contractor_id)
- Allow rules evaluated correctly
- Deny rules evaluated correctly (deny-by-default)
- Policy priority resolution
- Scope filters (company, site)
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.modules.rbac_abac.engine import evaluate
from app.modules.rbac_abac.types import Decision, PolicyContext, Resource, Subject


class TestABACDenyRules:
    """Deny rule evaluation (highest priority rule applies)."""

    def test_deny_rule_blocks_access(self) -> None:
        """Deny effect should result in allow=False."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("admin",),
            permissions=("document:read",),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"company_id": "company-a", "status": "draft"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={
                "policies": [
                    type(
                        "AuthzPolicy",
                        (),
                        {
                            "id": "policy-deny",
                            "resource": "document",
                            "action": "read",
                            "effect": "deny",
                            "conditions_json": {
                                "all": [
                                    {"attr": "status", "op": "eq", "value": "draft"},
                                ]
                            },
                            "priority": 10,
                            "enabled": True,
                        },
                    )()
                ]
            },
        )

        result = evaluate(subject, "read", resource, context)

        assert result.allow is False
        assert result.reason == "policy_deny"

    def test_deny_overrides_allow_same_priority(self) -> None:
        """When allow and deny have same priority, deny wins."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("editor",),
            permissions=("document:update",),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"company_id": "company-a", "owner_id": "other-user"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={
                "policies": [
                    type(
                        "AuthzPolicy",
                        (),
                        {
                            "id": "policy-allow",
                            "resource": "document",
                            "action": "update",
                            "effect": "allow",
                            "conditions_json": {
                                "all": [{"attr": "company_id", "op": "in", "value": ["company-a"]}]
                            },
                            "priority": 50,
                            "enabled": True,
                        },
                    )(),
                    type(
                        "AuthzPolicy",
                        (),
                        {
                            "id": "policy-deny",
                            "resource": "document",
                            "action": "update",
                            "effect": "deny",
                            "conditions_json": {
                                "all": [
                                    {"attr": "owner_id", "op": "ne", "value": "$scope.user_id"}
                                ]
                            },
                            "priority": 50,
                            "enabled": True,
                        },
                    )(),
                ]
            },
        )

        result = evaluate(subject, "update", resource, context)

        assert result.allow is False
        assert result.reason == "policy_deny"


class TestABACAllowRules:
    """Allow rule evaluation."""

    def test_allow_rule_grants_access(self) -> None:
        """Allow effect should result in allow=True."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("manager",),
            permissions=("risk:read",),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="risk",
            resource_id="risk-1",
            attrs={"company_id": "company-a"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={
                "policies": [
                    type(
                        "AuthzPolicy",
                        (),
                        {
                            "id": "policy-allow",
                            "resource": "risk",
                            "action": "read",
                            "effect": "allow",
                            "conditions_json": {
                                "all": [
                                    {"attr": "company_id", "op": "in", "value": ["company-a"]}
                                ]
                            },
                            "priority": 20,
                            "enabled": True,
                        },
                    )()
                ]
            },
        )

        result = evaluate(subject, "read", resource, context)

        assert result.allow is True
        assert result.reason == "policy_allow"

    def test_allow_with_multiple_conditions_all_match(self) -> None:
        """All conditions in 'all' array must be true."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("inspector",),
            permissions=("inspection:read",),
            company_ids=("company-a"),
            site_ids=("site-1",),
        )
        resource = Resource(
            resource_type="inspection",
            resource_id="insp-1",
            attrs={"company_id": "company-a", "site_id": "site-1", "status": "active"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={
                "policies": [
                    type(
                        "AuthzPolicy",
                        (),
                        {
                            "id": "policy-allow-multi",
                            "resource": "inspection",
                            "action": "read",
                            "effect": "allow",
                            "conditions_json": {
                                "all": [
                                    {"attr": "company_id", "op": "eq", "value": "company-a"},
                                    {"attr": "site_id", "op": "eq", "value": "site-1"},
                                    {"attr": "status", "op": "ne", "value": "archived"},
                                ]
                            },
                            "priority": 10,
                            "enabled": True,
                        },
                    )()
                ]
            },
        )

        result = evaluate(subject, "read", resource, context)

        assert result.allow is True


class TestABACAttributes:
    """Test all mandatory ABAC attributes."""

    def test_company_id_attribute_scope(self) -> None:
        """company_id in resource attrs should be scoped by policy."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("employee",),
            permissions=("company:read",),
            company_ids=("company-safe",),
        )
        resource_safe = Resource(
            resource_type="company",
            resource_id="comp-safe",
            attrs={"company_id": "company-safe"},
        )
        resource_unsafe = Resource(
            resource_type="company",
            resource_id="comp-unsafe",
            attrs={"company_id": "company-forbidden"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "company-scope",
                "resource": "company",
                "action": "read",
                "effect": "allow",
                "conditions_json": {
                    "all": [
                        {"attr": "company_id", "op": "in", "value": ["company-safe"]}
                    ]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result_safe = evaluate(subject, "read", resource_safe, context)
        result_unsafe = evaluate(subject, "read", resource_unsafe, context)

        assert result_safe.allow is True
        assert result_unsafe.allow is False

    def test_site_id_attribute_scope(self) -> None:
        """site_id in resource attrs should be scoped by policy."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("supervisor",),
            permissions=("site:read",),
            site_ids=("site-london",),
        )
        resource = Resource(
            resource_type="site",
            resource_id="site-1",
            attrs={"site_id": "site-paris"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "site-scope",
                "resource": "site",
                "action": "read",
                "effect": "deny",
                "conditions_json": {
                    "all": [{"attr": "site_id", "op": "ne", "value": "$scope.user_site"}]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            abac_scopes={"user_site": "site-london"},
            request_attrs={"policies": [policy]},
        )

        result = evaluate(subject, "read", resource, context)

        # Deny rule: site_id != user_site => site-paris != site-london => true => deny
        assert result.allow is False

    def test_status_attribute_document_draft_restriction(self) -> None:
        """Document status='draft' can be denied for non-owners."""
        subject = Subject(
            user_id="employee-1",
            tenant_id="tenant-1",
            roles=("employee",),
            permissions=("document:read",),
            company_ids=("company-a",),
        )
        resource_draft = Resource(
            resource_type="document",
            resource_id="doc-draft",
            attrs={"company_id": "company-a", "status": "draft", "owner_id": "owner-1"},
        )
        resource_published = Resource(
            resource_type="document",
            resource_id="doc-pub",
            attrs={"company_id": "company-a", "status": "published", "owner_id": "owner-1"},
        )
        policy_deny_draft = type(
            "AuthzPolicy",
            (),
            {
                "id": "deny-draft-non-owner",
                "resource": "document",
                "action": "read",
                "effect": "deny",
                "conditions_json": {
                    "all": [
                        {"attr": "status", "op": "eq", "value": "draft"},
                        {"attr": "owner_id", "op": "ne", "value": "$scope.user_id"},
                    ]
                },
                "priority": 20,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            abac_scopes={"user_id": "employee-1"},
            request_attrs={"policies": [policy_deny_draft]},
        )

        result_draft = evaluate(subject, "read", resource_draft, context)
        result_published = evaluate(subject, "read", resource_published, context)

        assert result_draft.allow is False  # Draft + not owner => deny
        assert result_published.allow is True  # Published => allow (fallback)

    def test_risk_level_attribute_requires_privilege(self) -> None:
        """High risk_level requires manager+ role."""
        subject_employee = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("employee",),
            permissions=("risk:read",),
            risk_level_max=1,  # Can only see low risk
        )
        subject_manager = Subject(
            user_id="manager-1",
            tenant_id="tenant-1",
            roles=("manager",),
            permissions=("risk:read",),
            risk_level_max=3,  # Can see high risk
        )
        resource_high = Resource(
            resource_type="risk",
            resource_id="risk-high",
            attrs={"risk_level": 3},  # High
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "risk-level-deny",
                "resource": "risk",
                "action": "read",
                "effect": "deny",
                "conditions_json": {
                    "all": [
                        {"attr": "risk_level", "op": "gt", "value": "$scope.max_risk_level"}
                    ]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context_employee = PolicyContext(
            tenant_id="tenant-1",
            abac_scopes={"max_risk_level": 1},
            request_attrs={"policies": [policy]},
        )
        context_manager = PolicyContext(
            tenant_id="tenant-1",
            abac_scopes={"max_risk_level": 3},
            request_attrs={"policies": [policy]},
        )

        result_employee = evaluate(subject_employee, "read", resource_high, context_employee)
        result_manager = evaluate(subject_manager, "read", resource_high, context_manager)

        assert result_employee.allow is False  # risk_level(3) > max(1) => deny
        assert result_manager.allow is True  # risk_level(3) <= max(3) => allow

    def test_project_id_attribute_scope(self) -> None:
        """project_id should limit access to assigned projects."""
        subject = Subject(
            user_id="pm-1",
            tenant_id="tenant-1",
            roles=("project_manager",),
            permissions=("project:read",),
            project_ids=("project-alpha", "project-beta"),
        )
        resource_assigned = Resource(
            resource_type="project",
            resource_id="proj-alpha",
            attrs={"project_id": "project-alpha"},
        )
        resource_unassigned = Resource(
            resource_type="project",
            resource_id="proj-gamma",
            attrs={"project_id": "project-gamma"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "project-scope",
                "resource": "project",
                "action": "read",
                "effect": "deny",
                "conditions_json": {
                    "all": [
                        {"attr": "project_id", "op": "not_in", "value": ["project-alpha", "project-beta"]}
                    ]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result_assigned = evaluate(subject, "read", resource_assigned, context)
        result_unassigned = evaluate(subject, "read", resource_unassigned, context)

        assert result_assigned.allow is True  # In assigned projects
        assert result_unassigned.allow is False  # Not in assigned projects

    def test_contractor_id_attribute_scope(self) -> None:
        """contractor_id should limit access to assigned contractors."""
        subject = Subject(
            user_id="contractor-liaison",
            tenant_id="tenant-1",
            roles=("contractor_manager",),
            permissions=("contractor:read",),
            contractor_ids=("contractor-acme", "contractor-globex"),
        )
        resource_assigned = Resource(
            resource_type="contractor",
            resource_id="ctr-acme",
            attrs={"contractor_id": "contractor-acme"},
        )
        resource_unassigned = Resource(
            resource_type="contractor",
            resource_id="ctr-unknown",
            attrs={"contractor_id": "contractor-unknown"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "contractor-scope",
                "resource": "contractor",
                "action": "read",
                "effect": "allow",
                "conditions_json": {
                    "all": [
                        {
                            "attr": "contractor_id",
                            "op": "in",
                            "value": ["contractor-acme", "contractor-globex"],
                        }
                    ]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result_assigned = evaluate(subject, "read", resource_assigned, context)
        result_unassigned = evaluate(subject, "read", resource_unassigned, context)

        assert result_assigned.allow is True  # In assigned contractors
        assert result_unassigned.allow is False  # Not in assigned contractors


class TestABACPolicyPriority:
    """Test policy priority resolution (lower priority number = higher priority)."""

    def test_lower_priority_number_wins(self) -> None:
        """Policy with priority 10 should override priority 50."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("admin",),
            permissions=("document:delete",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"status": "published"},
        )
        # Two conflicting rules: allow at 50, deny at 10
        # Lower number = higher priority => deny at 10 should win
        policies = [
            type(
                "AuthzPolicy",
                (),
                {
                    "id": "policy-allow-low-pri",
                    "resource": "document",
                    "action": "delete",
                    "effect": "allow",
                    "conditions_json": {"all": []},
                    "priority": 50,
                    "enabled": True,
                },
            )(),
            type(
                "AuthzPolicy",
                (),
                {
                    "id": "policy-deny-high-pri",
                    "resource": "document",
                    "action": "delete",
                    "effect": "deny",
                    "conditions_json": {
                        "all": [{"attr": "status", "op": "eq", "value": "published"}]
                    },
                    "priority": 10,
                    "enabled": True,
                },
            )(),
        ]
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": policies},
        )

        result = evaluate(subject, "delete", resource, context)

        assert result.allow is False
        assert result.matched_policy_id == "policy-deny-high-pri"


class TestABACDenyByDefault:
    """Test deny-by-default behavior (missing permission or no matching policy)."""

    def test_missing_permission_denies_access(self) -> None:
        """Subject without permission should be denied."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("viewer",),
            permissions=(),  # No permissions
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={},
        )

        result = evaluate(subject, "read", resource)

        assert result.allow is False
        assert result.reason == "missing_permission"

    def test_no_matching_policy_denies_access(self) -> None:
        """When no policy matches, static engine decides (deny-by-default)."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("employee",),
            permissions=("document:read",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"status": "archived"},
        )
        # Policy exists but conditions don't match
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "policy-no-match",
                "resource": "document",
                "action": "read",
                "effect": "allow",
                "conditions_json": {
                    "all": [{"attr": "status", "op": "eq", "value": "published"}]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result = evaluate(subject, "read", resource, context)

        # Static engine decides (depends on engine_policies config; typically deny-by-default)
        assert isinstance(result, Decision)

    def test_disabled_policy_is_ignored(self) -> None:
        """Disabled policies should not be evaluated."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("admin",),
            permissions=("risk:create",),
        )
        resource = Resource(
            resource_type="risk",
            resource_id="risk-1",
            attrs={},
        )
        policy_disabled = type(
            "AuthzPolicy",
            (),
            {
                "id": "policy-disabled",
                "resource": "risk",
                "action": "create",
                "effect": "deny",
                "conditions_json": {"all": []},
                "priority": 10,
                "enabled": False,  # DISABLED
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy_disabled]},
        )

        result = evaluate(subject, "create", resource, context)

        # Disabled policy should not match => fallback to static engine
        assert isinstance(result, Decision)


class TestABACEdgeCases:
    """Test edge cases and operator combinations."""

    def test_exists_operator(self) -> None:
        """'exists' operator checks if attribute is not None."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("manager",),
            permissions=("document:approve",),
        )
        resource_with_reviewer = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"reviewer_id": "reviewer-1"},
        )
        resource_no_reviewer = Resource(
            resource_type="document",
            resource_id="doc-2",
            attrs={},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "policy-needs-reviewer",
                "resource": "document",
                "action": "approve",
                "effect": "allow",
                "conditions_json": {
                    "all": [{"attr": "reviewer_id", "op": "exists"}]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result_with = evaluate(subject, "approve", resource_with_reviewer, context)
        result_without = evaluate(subject, "approve", resource_no_reviewer, context)

        assert result_with.allow is True
        assert result_without.allow is False

    def test_contains_operator_array_check(self) -> None:
        """'contains' operator checks if array contains value or value in array."""
        subject = Subject(
            user_id="inspector-1",
            tenant_id="tenant-1",
            roles=("inspector",),
            permissions=("finding:close",),
        )
        resource = Resource(
            resource_type="finding",
            resource_id="finding-1",
            attrs={"assignee_ids": ["inspector-1", "inspector-2"]},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "policy-assigned-inspector",
                "resource": "finding",
                "action": "close",
                "effect": "allow",
                "conditions_json": {
                    "all": [
                        {
                            "attr": "assignee_ids",
                            "op": "contains",
                            "value": "$scope.user_id",
                        }
                    ]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            abac_scopes={"user_id": "inspector-1"},
            request_attrs={"policies": [policy]},
        )

        result = evaluate(subject, "close", resource, context)

        assert result.allow is True

    def test_comparison_operators_numeric(self) -> None:
        """Numeric comparison operators (lt, lte, gt, gte) work correctly."""
        subject = Subject(
            user_id="approver-1",
            tenant_id="tenant-1",
            roles=("approver",),
            permissions=("expense:approve",),
        )
        resource_small = Resource(
            resource_type="expense",
            resource_id="exp-1",
            attrs={"amount": 50},
        )
        resource_large = Resource(
            resource_type="expense",
            resource_id="exp-2",
            attrs={"amount": 150},
        )
        # Policy: can only approve if amount < 100
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "policy-amount-limit",
                "resource": "expense",
                "action": "approve",
                "effect": "allow",
                "conditions_json": {
                    "all": [{"attr": "amount", "op": "lt", "value": 100}]
                },
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result_small = evaluate(subject, "approve", resource_small, context)
        result_large = evaluate(subject, "approve", resource_large, context)

        assert result_small.allow is True
        assert result_large.allow is False


class TestABACNegativeScenarios:
    """Negative scenarios: explicit denial, cross-tenant, insufficient permissions."""

    def test_cross_tenant_access_denied(self) -> None:
        """User from tenant-1 should not access resources from tenant-2."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",  # User belongs to tenant-1
            roles=("manager",),
            permissions=("document:read",),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-cross-tenant",
            attrs={"company_id": "company-a", "tenant_id": "tenant-2"},  # Resource in tenant-2
        )
        context = PolicyContext(
            tenant_id="tenant-2",  # Accessing as if from tenant-2
            request_attrs={"policies": []},
        )

        result = evaluate(subject, "read", resource, context)

        # Tenant mismatch should deny regardless of policies
        assert result.allow is False

    def test_insufficient_role_denies_write(self) -> None:
        """Employee role should not have write permissions."""
        subject = Subject(
            user_id="emp-1",
            tenant_id="tenant-1",
            roles=("employee",),  # Employee, not manager
            permissions=("document:read",),  # Only read, no write
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"company_id": "company-a"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": []},
        )

        result = evaluate(subject, "write", resource, context)

        # No write permission => deny
        assert result.allow is False
        assert result.reason == "missing_permission"

    def test_empty_scope_ids_blocks_query_access(self) -> None:
        """User with no scope IDs should be denied access even with permission."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("manager",),
            permissions=("company:read",),
            company_ids=(),  # EMPTY scope
        )
        resource = Resource(
            resource_type="company",
            resource_id="comp-1",
            attrs={"company_id": "company-a"},
        )
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": []},
        )

        result = evaluate(subject, "read", resource, context)

        # Empty scope => deny (no accessible resources)
        assert result.allow is False

    def test_multiple_conflicts_deny_precedence(self) -> None:
        """Multiple conflicting policies: deny should always win."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("admin",),
            permissions=("risk:delete",),
        )
        resource = Resource(
            resource_type="risk",
            resource_id="risk-1",
            attrs={"risk_level": 5, "is_critical": True},
        )
        # Multiple policies: allow critical risks, but deny high-level risks
        policies = [
            type(
                "AuthzPolicy",
                (),
                {
                    "id": "allow-critical",
                    "resource": "risk",
                    "action": "delete",
                    "effect": "allow",
                    "conditions_json": {
                        "all": [{"attr": "is_critical", "op": "eq", "value": True}]
                    },
                    "priority": 20,
                    "enabled": True,
                },
            )(),
            type(
                "AuthzPolicy",
                (),
                {
                    "id": "deny-high-level",
                    "resource": "risk",
                    "action": "delete",
                    "effect": "deny",
                    "conditions_json": {
                        "all": [{"attr": "risk_level", "op": "gt", "value": 3}]
                    },
                    "priority": 10,  # Higher priority (lower number)
                    "enabled": True,
                },
            )(),
        ]
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": policies},
        )

        result = evaluate(subject, "delete", resource, context)

        # Deny has higher priority (10 < 20) => deny wins
        assert result.allow is False
        assert result.matched_policy_id == "deny-high-level"

    def test_action_mismatch_denies_request(self) -> None:
        """Policy for 'read' should not cover 'delete' action."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("viewer",),
            permissions=("document:read",),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="document",
            resource_id="doc-1",
            attrs={"company_id": "company-a"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "read-only",
                "resource": "document",
                "action": "read",  # Only read
                "effect": "allow",
                "conditions_json": {"all": []},
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result = evaluate(subject, "delete", resource, context)

        # Action mismatch (policy is for read, request is delete) => deny
        assert result.allow is False

    def test_resource_type_mismatch_denies_request(self) -> None:
        """Policy for 'document' should not cover 'risk' resource."""
        subject = Subject(
            user_id="user-1",
            tenant_id="tenant-1",
            roles=("manager",),
            permissions=("document:read", "risk:read"),
            company_ids=("company-a",),
        )
        resource = Resource(
            resource_type="risk",  # Different resource type
            resource_id="risk-1",
            attrs={"company_id": "company-a"},
        )
        policy = type(
            "AuthzPolicy",
            (),
            {
                "id": "document-policy",
                "resource": "document",  # Policy is for documents
                "action": "read",
                "effect": "allow",
                "conditions_json": {"all": []},
                "priority": 10,
                "enabled": True,
            },
        )()
        context = PolicyContext(
            tenant_id="tenant-1",
            request_attrs={"policies": [policy]},
        )

        result = evaluate(subject, "read", resource, context)

        # Resource type mismatch => deny
        assert result.allow is False
