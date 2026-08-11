"""Backend access matrix enforcement tests for RC-006 (E2E diagnostics)."""

from __future__ import annotations

import pytest

from app.core.rbac_abac import ActorContext, policy_engine
from app.models.models import RoleEnum
from app.modules.rbac_abac.engine import evaluate
from app.modules.rbac_abac.types import Resource, Subject


class TestOwnerAdminBroadInTenant:
    """Owner/admin broad in-tenant access (positive: can do everything)."""

    def test_owner_can_do_everything_in_tenant(self) -> None:
        """Owner should have broad read/write/delete within tenant."""
        owner = ActorContext(
            user_id="owner-1",
            tenant_id="t-1",
            roles=(RoleEnum.OWNER.value,),
        )

        # Should allow: read documents
        decision = policy_engine.can(owner, action="read", resource="documents")
        assert decision.allowed is True, "Owner should be able to read documents"

        # Should allow: write/create documents
        decision = policy_engine.can(owner, action="write", resource="documents")
        assert decision.allowed is True, "Owner should be able to write documents"

        # Should allow: delete documents
        decision = policy_engine.can(owner, action="delete", resource="documents")
        assert decision.allowed is True, "Owner should be able to delete documents"

    def test_cross_tenant_write_is_rejected(self) -> None:
        """Owner of one tenant cannot modify resources of another tenant."""
        owner_t1 = ActorContext(
            user_id="owner-1",
            tenant_id="t-1",
            roles=(RoleEnum.OWNER.value,),
        )

        # Try to write to a resource in a different tenant context
        decision = policy_engine.can(
            actor=owner_t1,
            action="write",
            resource="documents",
            ctx={"tenant_id": "t-2"},  # Different tenant
        )
        assert decision.allowed is False, "Cross-tenant write should be rejected"


class TestAuditorReadOnly:
    """Auditor read-only access enforcement."""

    def test_auditor_ro_cannot_create_or_update(self) -> None:
        """Auditor role should only have read permissions."""
        auditor = Subject(
            user_id="auditor-1",
            tenant_id="t-1",
            roles=(RoleEnum.AUDITOR_RO.value,),
            # Read-only role: production derives read perms from the role, and the
            # permission-based engine needs them on the Subject to pass the
            # precondition. No write perms -> create/update/delete still denied.
            permissions=("documents:read",),
        )

        # Should allow: read
        decision = evaluate(auditor, "read", Resource(resource_type="documents"))
        assert decision.allow is True, "Auditor should be able to read"

        # Should deny: create
        decision = evaluate(auditor, "create", Resource(resource_type="documents"))
        assert decision.allow is False, "Auditor should not be able to create"

        # Should deny: update
        decision = evaluate(auditor, "update", Resource(resource_type="documents"))
        assert decision.allow is False, "Auditor should not be able to update"

        # Should deny: delete
        decision = evaluate(auditor, "delete", Resource(resource_type="documents"))
        assert decision.allow is False, "Auditor should not be able to delete"


class TestStudentInstructorTraining:
    """Student/Instructor role permissions for training domain."""

    def test_direct_api_create_is_denied_for_low_privilege_user(self) -> None:
        """Student role should not be able to create training records directly."""
        student = Subject(
            user_id="student-1",
            tenant_id="t-1",
            roles=(RoleEnum.STUDENT.value,),
            permissions=(),
        )

        decision = evaluate(student, "create", Resource(resource_type="training"))
        assert decision.allow is False, "Student should not be able to create training"


class TestScopeBasedABAC:
    """Attribute-Based Access Control (ABAC) scope enforcement."""

    def test_inspector_contractor_reads_within_contractor(self) -> None:
        """Contractor inspector should only read within assigned contractor scope."""
        inspector = ActorContext(
            user_id="insp-1",
            tenant_id="t-1",
            roles=(RoleEnum.INSPECTOR_CONTRACTOR.value,),
            contractor_ids=("ctr-1",),
        )

        # Should allow: read within contractor scope
        decision = policy_engine.can(
            actor=inspector,
            action="read",
            resource="contractors",
            ctx={"contractor_id": "ctr-1"},
        )
        assert decision.allowed is True, "Inspector should read within assigned contractor"

    def test_hse_specialist_denied_on_foreign_company(self) -> None:
        """HSE specialist should be denied access to companies outside their scope."""
        hse_specialist = Subject(
            user_id="hse-1",
            tenant_id="t-1",
            roles=("ot_specialist",),
            permissions=("read:site", "read:risk_map"),
            company_ids=("comp-1",),  # Scoped to specific company
        )

        # Should deny: access to different company
        decision = evaluate(
            hse_specialist,
            "read",
            Resource(
                resource_type="risk_map",
                attrs={"company_id": "comp-2"},  # Different company
            ),
        )
        assert decision.allow is False, "HSE specialist should be denied foreign company access"


class TestCrossTenantDeny:
    """Cross-tenant isolation enforcement."""

    def test_cross_tenant_header_is_denied_even_for_privileged_user(self) -> None:
        """Even privileged users should not access other tenants via X-Tenant header manipulation."""
        admin_t1 = ActorContext(
            user_id="admin-1",
            tenant_id="t-1",
            roles=(RoleEnum.ADMIN.value,),
        )

        # Should deny: attempt to access t-2 when user belongs to t-1
        decision = policy_engine.can(
            actor=admin_t1,
            action="read",
            resource="documents",
            ctx={"tenant_id": "t-2"},  # User not in t-2
        )
        assert decision.allowed is False, "Cross-tenant access should be denied"


class TestFileAccessDeny:
    """File-level access control enforcement."""

    def test_file_detail_denies_client_from_other_company(self) -> None:
        """File access should be scoped to same company."""
        user_comp1 = Subject(
            user_id="user-1",
            tenant_id="t-1",
            roles=(RoleEnum.EMPLOYEE.value,),
            permissions=("read:file",),
            company_ids=("comp-1",),
        )

        # Should deny: access file from different company
        decision = evaluate(
            user_comp1,
            "read",
            Resource(resource_type="file", attrs={"company_id": "comp-2"}),
        )
        assert decision.allow is False, "Cross-company file access should be denied"


class TestSessionPrivilegeReuse:
    """Session token and privilege escalation denial."""

    def test_stale_admin_token_is_denied_after_role_downgrade(self) -> None:
        """User downgraded from admin should not retain admin privileges."""
        # Simulate: user was admin (old token), now is employee (new state)
        user_now_employee = Subject(
            user_id="user-1",
            tenant_id="t-1",
            roles=(RoleEnum.EMPLOYEE.value,),  # Downgraded role
            permissions=("read:documents",),
        )

        # Should deny: admin-level action with employee role
        decision = evaluate(user_now_employee, "delete", Resource(resource_type="documents"))
        assert decision.allow is False, "Downgraded user should not retain admin privileges"


class TestMandatorySmokeTests:
    """Minimal smoke tests (no external credentials required)."""

    def test_any_route_requires_tenant_header(self) -> None:
        """All business routes should require X-Tenant header."""
        # This is validated at middleware level, but test documents the requirement
        pytest.skip("Middleware-level validation; verified at integration test level")

    def test_login_page_renders(self) -> None:
        """Login endpoint should be accessible without authentication."""
        pytest.skip("Frontend smoke test; run via Playwright in CI")

    def test_protected_route_redirects_to_login_when_logged_out(self) -> None:
        """Protected routes should redirect unauthenticated users."""
        pytest.skip("Frontend smoke test; run via Playwright in CI")

    def test_unauthorized_route_shows_access_denied(self) -> None:
        """User without permission should see access denied page."""
        pytest.skip("Frontend smoke test; run via Playwright in CI")
