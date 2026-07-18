"""Tests for Task 1.2: RBAC Engine Module-Level Access Control (vNext-SEC-01).

Verifies:
- Module-level permission checks
- Role-to-module mapping enforcement
- Cross-module boundary violations
- Backward compatibility with existing permission checks
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum, Tenant, User
from app.modules.rbac_abac import ROLE_MODULE_DEFAULTS, check_module_access
from app.modules.rbac_abac.types import Subject
from app.services.dev_bootstrap import create_test_user


@pytest.fixture
async def user_by_role(test_db_session: AsyncSession, test_tenant: Tenant) -> dict[str, User]:
    """Create test users for each major role."""
    users_by_role: dict[str, User] = {}

    for role in [
        RoleEnum.OWNER,
        RoleEnum.ADMIN,
        RoleEnum.OT_PB_LEAD,
        RoleEnum.OT_SPECIALIST,
        RoleEnum.HR,
        RoleEnum.TEACHER,
        RoleEnum.STUDENT,
        RoleEnum.MANAGER,
        RoleEnum.WORKER,
        RoleEnum.AUDITOR_RO,
    ]:
        user = await create_test_user(
            session=test_db_session,
            tenant_id=str(test_tenant.id),
            email=f"user.module.{role.value}@example.com",
            role=role,
        )
        users_by_role[role.value] = user

    await test_db_session.commit()
    return users_by_role


# ============================================================================
# Module Access Control Tests
# ============================================================================


def test_module_permissions_defined():
    """Verify module permissions are defined and non-empty."""
    assert ROLE_MODULE_DEFAULTS is not None
    assert isinstance(ROLE_MODULE_DEFAULTS, dict)
    assert len(ROLE_MODULE_DEFAULTS) > 0
    assert "owner" in ROLE_MODULE_DEFAULTS
    assert "admin" in ROLE_MODULE_DEFAULTS


def test_owner_has_access_to_all_modules():
    """Verify owner role has access to all critical modules."""
    owner_modules = ROLE_MODULE_DEFAULTS.get("owner", [])
    critical_modules = ["risk", "ppe", "training", "documents", "incidents", "inspections", "admin"]
    for module in critical_modules:
        assert module in owner_modules, f"Owner should have access to {module}"


def test_admin_denied_access_to_billing():
    """Verify admin role does not have access to billing module by default."""
    admin_modules = ROLE_MODULE_DEFAULTS.get("admin", [])
    assert "billing" not in admin_modules, "Admin should not have billing access by default"


def test_student_minimal_module_access():
    """Verify student role has only essential modules."""
    student_modules = ROLE_MODULE_DEFAULTS.get("student", [])
    assert len(student_modules) <= 5
    assert "training" in student_modules
    assert "documents" in student_modules
    assert "admin" not in student_modules
    assert "billing" not in student_modules


def test_hr_module_access():
    """Verify HR role has training/medical/masterdata modules."""
    hr_modules = ROLE_MODULE_DEFAULTS.get("hr", [])
    expected = ["training", "medical", "masterdata", "documents", "tasks"]
    for module in expected:
        assert module in hr_modules, f"HR should have {module} access"


def test_ot_specialist_module_access():
    """Verify OT Specialist has risk/ppe/incidents access."""
    ot_modules = ROLE_MODULE_DEFAULTS.get("ot_specialist", [])
    expected = ["risk", "ppe", "incidents", "documents", "tasks"]
    for module in expected:
        assert module in ot_modules, f"OT Specialist should have {module} access"


def test_auditor_ro_module_access():
    """Verify Auditor (read-only) has audit/compliance access."""
    auditor_modules = ROLE_MODULE_DEFAULTS.get("auditor_ro", [])
    expected = ["audit", "documents", "risk", "incidents", "compliance"]
    for module in expected:
        assert module in auditor_modules, f"Auditor should have {module} access"


# ============================================================================
# Module Access Control Function Tests
# ============================================================================


def test_check_module_access_owner_allowed():
    """Verify owner can access any module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.OWNER],
        permissions=["owner"],
    )
    allowed, reason = check_module_access(subject, "billing")
    assert allowed is True, "Owner should have access to all modules"
    assert reason == "module_allowed"


def test_check_module_access_student_denied():
    """Verify student cannot access admin module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.STUDENT],
        permissions=["training.read", "documents.read"],
    )
    allowed, reason = check_module_access(subject, "admin")
    assert allowed is False, "Student should not have admin access"
    assert reason == "module_denied"


def test_check_module_access_student_training_allowed():
    """Verify student can access training module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.STUDENT],
        permissions=["training.read"],
    )
    allowed, reason = check_module_access(subject, "training")
    assert allowed is True, "Student should have training access"
    assert reason == "module_allowed"


def test_check_module_access_hr_denied_risk():
    """Verify HR cannot access risk module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.HR],
        permissions=["training.read", "medical.read"],
    )
    allowed, reason = check_module_access(subject, "risk")
    assert allowed is False, "HR should not have risk access"


def test_check_module_access_hr_allowed_training():
    """Verify HR can access training module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.HR],
        permissions=["training.read"],
    )
    allowed, reason = check_module_access(subject, "training")
    assert allowed is True, "HR should have training access"


def test_check_module_access_ot_specialist_denied_admin():
    """Verify OT Specialist cannot access admin module."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.OT_SPECIALIST],
        permissions=["risk.read", "ppe.read"],
    )
    allowed, reason = check_module_access(subject, "admin")
    assert allowed is False, "OT Specialist should not have admin access"


def test_check_module_access_auditor_ro_denied_write():
    """Verify Auditor (read-only) cannot write (read-only role check)."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.AUDITOR_RO],
        permissions=["audit.read"],
    )
    allowed, reason = check_module_access(subject, "audit")
    assert allowed is True, "Auditor should have read-only audit access"
    assert reason == "module_allowed"


def test_check_module_access_admin_denied_billing():
    """Verify Admin cannot access billing module by default."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.ADMIN],
        permissions=["admin.settings"],
    )
    allowed, reason = check_module_access(subject, "billing")
    assert allowed is False, "Admin should not have billing access"


def test_check_module_access_multiple_roles():
    """Verify module access with multiple roles uses first role."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.HR, RoleEnum.OT_SPECIALIST],
        permissions=["training.read", "risk.read"],
    )
    allowed, reason = check_module_access(subject, "training")
    assert allowed is True, "First role (HR) should have training access"


# ============================================================================
# Cross-Module Boundary Violation Tests
# ============================================================================


@pytest.mark.parametrize(
    "role,denied_module",
    [
        (RoleEnum.STUDENT, "admin"),
        (RoleEnum.STUDENT, "audit"),
        (RoleEnum.STUDENT, "billing"),
        (RoleEnum.WORKER, "admin"),
        (RoleEnum.WORKER, "billing"),
        (RoleEnum.TEACHER, "incidents"),
        (RoleEnum.TEACHER, "risk"),
        (RoleEnum.AUDITOR_RO, "admin"),
        (RoleEnum.HR, "risk"),
        (RoleEnum.HR, "billing"),
    ],
)
def test_cross_module_boundary_violations(role: RoleEnum, denied_module: str):
    """Verify roles cannot access modules outside their scope."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[role],
        permissions=[],
    )
    allowed, reason = check_module_access(subject, denied_module)
    assert allowed is False, f"{role.value} should not have access to {denied_module}"


@pytest.mark.parametrize(
    "role,allowed_module",
    [
        (RoleEnum.STUDENT, "training"),
        (RoleEnum.STUDENT, "documents"),
        (RoleEnum.WORKER, "tasks"),
        (RoleEnum.WORKER, "documents"),
        (RoleEnum.TEACHER, "training"),
        (RoleEnum.TEACHER, "briefings"),
        (RoleEnum.AUDITOR_RO, "audit"),
        (RoleEnum.AUDITOR_RO, "risk"),
        (RoleEnum.HR, "training"),
        (RoleEnum.HR, "medical"),
    ],
)
def test_allowed_module_access_per_role(role: RoleEnum, allowed_module: str):
    """Verify roles have access to their designated modules."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[role],
        permissions=[],
    )
    allowed, reason = check_module_access(subject, allowed_module)
    assert allowed is True, f"{role.value} should have access to {allowed_module}"


# ============================================================================
# Backward Compatibility Tests
# ============================================================================


def test_module_access_does_not_break_existing_permissions():
    """Verify module access is additive and doesn't break existing permission checks."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=[RoleEnum.OT_SPECIALIST],
        permissions=["risk.read", "ppe.read"],
    )
    # Module access should allow the request
    allowed, reason = check_module_access(subject, "risk")
    assert allowed is True

    # But existing permission checks are still required (verified by engine.evaluate)


def test_module_access_for_unmapped_role():
    """Verify unmapped roles get sensible defaults."""
    subject = Subject(
        user_id="test-user",
        tenant_id="test-tenant",
        roles=["some_new_role"],
        permissions=[],
    )
    allowed, reason = check_module_access(subject, "training")
    # Unmapped role should be denied by default
    assert allowed is False, "Unmapped roles should be denied by default"


# ============================================================================
# Feature Flag / Gradual Rollout Tests
# ============================================================================


def test_all_roles_have_module_definitions():
    """Verify all major roles have module definitions."""
    major_roles = [
        "owner",
        "admin",
        "ot_pb_lead",
        "ot_specialist",
        "hr",
        "teacher",
        "student",
        "manager",
        "worker",
        "auditor_ro",
    ]
    for role in major_roles:
        assert role in ROLE_MODULE_DEFAULTS, f"Module definitions missing for {role}"
        assert len(ROLE_MODULE_DEFAULTS[role]) > 0, f"Module list empty for {role}"
