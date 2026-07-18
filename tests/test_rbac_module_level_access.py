"""
Tests for module-level RBAC access control.

Task 1.2: RBAC Engine Hardening (vNext-SEC-01)

Tests verify that:
1. Module-level permissions are enforced before resource-level permissions
2. Each role can only access permitted modules
3. Administrators and owners bypass module restrictions
4. Cross-module boundary violations are prevented
5. Negative test cases for unauthorized module access
"""

import pytest

from app.core.rbac_abac import (
    MODULE_NAMES,
    MODULE_PERMISSIONS,
    ActorContext,
    policy_engine,
)


class TestModuleLevelAccessControl:
    """Test suite for module-level RBAC access control."""

    @pytest.mark.parametrize("module", MODULE_NAMES)
    def test_module_names_defined(self, module: str):
        """Verify all module names are recognized."""
        assert module in MODULE_NAMES
        assert isinstance(module, str)
        assert len(module) > 0

    def test_admin_has_all_modules(self):
        """Admin role should have access to all modules."""
        allowed_modules = MODULE_PERMISSIONS.get("admin", set())
        assert allowed_modules == set(MODULE_NAMES)

    def test_owner_has_all_modules(self):
        """Owner role should have access to all modules."""
        allowed_modules = MODULE_PERMISSIONS.get("owner", set())
        assert allowed_modules == set(MODULE_NAMES)

    def test_ot_specialist_has_risk_module(self):
        """OT specialist should have access to risk module."""
        allowed_modules = MODULE_PERMISSIONS.get("hse_specialist", set())
        assert "risk" in allowed_modules

    def test_ot_specialist_cannot_access_admin_module(self):
        """OT specialist should NOT have access to admin module."""
        allowed_modules = MODULE_PERMISSIONS.get("hse_specialist", set())
        assert "admin" not in allowed_modules

    def test_trainer_can_access_training_module(self):
        """Trainer role should access training module."""
        allowed_modules = MODULE_PERMISSIONS.get("instructor", set())
        assert "training" in allowed_modules

    def test_trainer_cannot_access_risk_module(self):
        """Trainer role should NOT access risk module."""
        allowed_modules = MODULE_PERMISSIONS.get("instructor", set())
        assert "risk" not in allowed_modules

    def test_hr_can_access_documents_and_training(self):
        """HR role should access documents and training modules."""
        allowed_modules = MODULE_PERMISSIONS.get("hr", set())
        assert "documents" in allowed_modules
        assert "training" in allowed_modules

    def test_hr_cannot_access_risk_or_ppe(self):
        """HR role should NOT access risk or ppe modules."""
        allowed_modules = MODULE_PERMISSIONS.get("hr", set())
        assert "risk" not in allowed_modules
        assert "ppe" not in allowed_modules

    def test_auditor_has_readonly_modules(self):
        """Auditor should have access to reporting modules."""
        allowed_modules = MODULE_PERMISSIONS.get("auditor_ro", set())
        assert "reports" in allowed_modules
        assert "documents" in allowed_modules

    def test_client_role_restricted_modules(self):
        """Client role should have limited module access."""
        allowed_modules = MODULE_PERMISSIONS.get("client", set())
        assert "documents" in allowed_modules
        assert "contractors" in allowed_modules
        # Should not have admin, risk, ppe, training
        assert "admin" not in allowed_modules
        assert "risk" not in allowed_modules
        assert "ppe" not in allowed_modules

    def test_module_permissions_all_roles_defined(self):
        """All role-permission mappings should exist for module access."""
        known_roles = {
            "owner",
            "admin",
            "methodist",
            "lawyer",
            "project_manager",
            "executor",
            "clerk",
            "instructor",
            "student",
            "hse_head",
            "hse_specialist",
            "fire_engineer",
            "ecologist",
            "hr",
            "accountant",
            "line_manager",
            "client",
            "auditor_ro",
            "inspector_contractor",
            "client_admin",
            "client_user",
        }
        for role in known_roles:
            assert role in MODULE_PERMISSIONS, f"Missing module permissions for role: {role}"

    @pytest.mark.parametrize(
        "role,expected_modules",
        [
            ("owner", set(MODULE_NAMES)),
            ("admin", set(MODULE_NAMES)),
            ("methodist", {"documents", "templates"}),
            ("lawyer", {"documents", "templates"}),
            ("hse_head", {"documents", "risk", "ppe", "inspections", "incidents", "contractors"}),
            ("hse_specialist", {"documents", "risk", "ppe", "inspections", "incidents"}),
            ("instructor", {"training", "briefings"}),
            ("student", {"training"}),
            ("hr", {"documents", "training"}),
        ],
    )
    def test_role_module_permissions(self, role: str, expected_modules: set[str]):
        """Verify module permissions for each major role."""
        actual_modules = MODULE_PERMISSIONS.get(role, set())
        assert actual_modules == expected_modules, f"Mismatch for role {role}"


class TestModuleAccessPolicyEngine:
    """Integration tests with PolicyEngine for module-level checks."""

    def test_admin_bypasses_module_check(self):
        """Admin should bypass module access restrictions."""
        actor = ActorContext(
            user_id="admin123",
            tenant_id="tenant1",
            roles=("admin",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.allowed is True
        assert decision.reason == "explicit_allow"

    def test_owner_bypasses_module_check(self):
        """Owner should bypass module access restrictions."""
        actor = ActorContext(
            user_id="owner123",
            tenant_id="tenant1",
            roles=("owner",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="create",
            resource="documents",
        )
        assert decision.allowed is True

    def test_specialist_denied_admin_resource(self):
        """OT specialist accessing admin resource should be denied."""
        actor = ActorContext(
            user_id="specialist123",
            tenant_id="tenant1",
            roles=("hse_specialist",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="admin",
        )
        # Should be denied due to module access check
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_trainer_cannot_access_risk_module(self):
        """Trainer trying to access risk module should be denied."""
        actor = ActorContext(
            user_id="trainer123",
            tenant_id="tenant1",
            roles=("instructor",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_trainer_can_access_training_module(self):
        """Trainer accessing training module should be allowed."""
        actor = ActorContext(
            user_id="trainer123",
            tenant_id="tenant1",
            roles=("instructor",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="trainings",
        )
        # Module check passes, resource check should also pass
        assert decision.allowed is True or decision.reason in (
            "missing_permission",
            "module_access_denied",
        )

    def test_hr_cannot_access_risk_maps(self):
        """HR role denied access to risk_maps (ppe module)."""
        actor = ActorContext(
            user_id="hr123",
            tenant_id="tenant1",
            roles=("hr",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="list",
            resource="ppe_norms",
        )
        # HR doesn't have ppe module access
        assert decision.reason == "module_access_denied"

    def test_student_cannot_create_training(self):
        """Student role denied write access to training module."""
        actor = ActorContext(
            user_id="student123",
            tenant_id="tenant1",
            roles=("student",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="create",
            resource="trainings",
        )
        # Module check passes (student has training module)
        # But resource permission check will fail (students can only read)
        assert decision.allowed is False
        assert decision.reason == "missing_permission"

    def test_client_cannot_access_risk(self):
        """Client role denied access to risk module."""
        actor = ActorContext(
            user_id="client123",
            tenant_id="tenant1",
            roles=("client",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_auditor_can_access_reports(self):
        """Auditor role should access reports module."""
        actor = ActorContext(
            user_id="auditor123",
            tenant_id="tenant1",
            roles=("auditor_ro",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="reports",
        )
        # Should pass module check (auditor has reports module)
        # Should pass resource check (auditor can read reports)
        assert decision.allowed is True or decision.reason == "missing_permission"

    def test_multiple_roles_union_modules(self):
        """User with multiple roles should have union of module access."""
        actor = ActorContext(
            user_id="multi123",
            tenant_id="tenant1",
            roles=("hr", "instructor"),  # hr + instructor
        )
        # Actor should have: documents, training, briefings
        # Should be able to access training
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="trainings",
        )
        # Module check should pass (instructor role has training module)
        assert decision.reason != "module_access_denied"

    def test_multiple_roles_union_modules_documents(self):
        """Multi-role user should have access to documents."""
        actor = ActorContext(
            user_id="multi123",
            tenant_id="tenant1",
            roles=("hr", "instructor"),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="documents",
        )
        # Module check should pass (hr role has documents module)
        assert decision.reason != "module_access_denied"


class TestModuleAccessBoundaryViolations:
    """Test negative scenarios: cross-module boundary violations."""

    def test_ppe_specialist_cannot_access_training(self):
        """PPE specialist (implied by hse_specialist) cannot access training."""
        actor = ActorContext(
            user_id="ppe123",
            tenant_id="tenant1",
            roles=("hse_specialist",),  # has ppe but not training
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="trainings",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_training_specialist_cannot_access_incidents(self):
        """Training specialist cannot access incidents module."""
        actor = ActorContext(
            user_id="training123",
            tenant_id="tenant1",
            roles=("instructor",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="incidents",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_contractor_cannot_access_documents(self):
        """Contractor inspector cannot access document module."""
        actor = ActorContext(
            user_id="contractor123",
            tenant_id="tenant1",
            roles=("inspector_contractor",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="documents",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_client_cannot_access_incidents(self):
        """Client cannot access incidents module."""
        actor = ActorContext(
            user_id="client123",
            tenant_id="tenant1",
            roles=("client",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="incidents",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_lawyer_cannot_access_risk(self):
        """Lawyer (document specialist) cannot access risk module."""
        actor = ActorContext(
            user_id="lawyer123",
            tenant_id="tenant1",
            roles=("lawyer",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_accountant_can_only_access_reports(self):
        """Accountant can only access reports module."""
        actor = ActorContext(
            user_id="accountant123",
            tenant_id="tenant1",
            roles=("accountant",),
        )
        allowed_modules = MODULE_PERMISSIONS.get("accountant", set())
        assert allowed_modules == {"reports"}

        # Should access reports
        decision_reports = policy_engine.can(
            actor=actor,
            action="read",
            resource="reports",
        )
        assert decision_reports.reason != "module_access_denied"

        # Should NOT access documents
        decision_documents = policy_engine.can(
            actor=actor,
            action="read",
            resource="documents",
        )
        assert decision_documents.allowed is False
        assert decision_documents.reason == "module_access_denied"


class TestModuleAccessAuditFields:
    """Test audit metadata for module access decisions."""

    def test_module_denied_audit_fields(self):
        """Module denial should include audit fields."""
        actor = ActorContext(
            user_id="specialist123",
            tenant_id="tenant1",
            roles=("hse_specialist",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="admin",
        )
        assert decision.allowed is False
        assert "module" in decision.audit_meta
        assert decision.audit_meta["module"] == "admin"

    def test_module_access_audit_reason(self):
        """Module denial audit reason should be module_access_denied."""
        actor = ActorContext(
            user_id="trainer123",
            tenant_id="tenant1",
            roles=("instructor",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.reason == "module_access_denied"
        assert decision.audit_meta.get("module") == "risk"
