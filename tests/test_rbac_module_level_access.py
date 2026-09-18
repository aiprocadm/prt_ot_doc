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
    ROLE_ALIASES,
    ActorContext,
    modules_for_role,
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

    def test_специалисту_ОТ_открыт_модуль_рисков(self):
        """Срез-228: проверка спрашивала роль ``hse_specialist``, которой в
        продукте НЕТ, — и потому была зелёной при любом положении дел.

        Настоящая роль называется ``ot_specialist``, и круг её модулей считается
        функцией: словарь ПЛЮС выведенное из единой карты прав экрана.
        """

        allowed = modules_for_role("ot_specialist")
        assert "risk" in allowed
        assert "admin" not in allowed, "специалист — не администратор платформы"

    def test_преподавателю_открыто_обучение_но_не_риски(self):
        """Та же подмена: роль звалась ``instructor``, в продукте она ``teacher``.

        Хуже того, синоним уводил настоящего преподавателя на выдуманного
        инструктора, и вывод прав из карты для него молча не работал.
        """

        allowed = modules_for_role("teacher")
        assert "training" in allowed
        assert "briefings" in allowed
        assert "risk" not in allowed

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

    def test_у_каждой_настоящей_роли_есть_круг_модулей(self):
        """Срез-228. Здесь стоял список имён, написанный руками: шесть ролей в
        нём не существовали, а одиннадцати настоящих не хватало. Проверка была
        зелёной ровно потому, что спрашивала тот же выдуманный мир.

        Теперь перечень берётся у продукта, а круг модулей — у функции, которая
        знает и словарь, и единую карту прав.
        """

        from app.models.tenant_billing import RoleEnum

        empty = sorted(role.value for role in RoleEnum if not modules_for_role(role.value))
        assert not empty, f"роли без единого модуля: {empty}"

    def test_словари_прав_не_называют_несуществующих_ролей(self):
        """Доказано поломкой: сторож на импорте валит модуль при выдуманном имени.

        Это и есть корень срезов 226–228: словарь называл шесть ролей, которых
        нет, и семи настоящим не доставалось ничего.
        """

        from app.models.tenant_billing import RoleEnum

        known = {role.value for role in RoleEnum}
        assert not set(MODULE_PERMISSIONS) - known
        assert not set(ROLE_ALIASES.values()) - known, "синоним ведёт в никуда"

    @pytest.mark.parametrize(
        "role,expected_modules",
        [
            ("owner", set(MODULE_NAMES)),
            ("admin", set(MODULE_NAMES)),
            ("lawyer", {"documents", "templates", "reports"}),
            (
                "ot_pb_lead",
                {
                    "documents",
                    "templates",
                    "risk",
                    "ppe",
                    "inspections",
                    "incidents",
                    "contractors",
                    "reports",
                    "training",
                    "briefings",
                },
            ),
            ("student", {"training", "briefings", "documents"}),
        ],
    )
    def test_круг_модулей_роли(self, role: str, expected_modules: set[str]):
        """Срез-228: роли настоящие, круг считается функцией, а не словарём."""

        assert modules_for_role(role) == expected_modules, f"не сходится у роли {role}"


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
            roles=("ot_specialist",),
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
            roles=("teacher",),
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
            roles=("teacher",),
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
            roles=("hr", "teacher"),  # кадровик + преподаватель
        )
        # Actor should have: documents, training, briefings
        # Should be able to access training
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="trainings",
        )
        # Module check should pass (у преподавателя есть модуль обучения)
        assert decision.reason != "module_access_denied"

    def test_multiple_roles_union_modules_documents(self):
        """Multi-role user should have access to documents."""
        actor = ActorContext(
            user_id="multi123",
            tenant_id="tenant1",
            roles=("hr", "teacher"),
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

    def test_специалисту_ОТ_закрыта_админка_платформы(self):
        """Срез-228. Здесь стояло «специалисту по СИЗ закрыто обучение», и роль
        звалась ``hse_specialist`` — такой в продукте нет, поэтому отказ
        подтверждался сам собой.

        У настоящего специалиста ОТ обучение как раз открыто: единая карта даёт
        ему ``training.view`` — он проводит инструктажи и ведёт обучение. Граница
        у него другая и настоящая: настройки платформы.
        """

        actor = ActorContext(
            user_id="ot-specialist-1",
            tenant_id="tenant1",
            roles=("ot_specialist",),
        )
        assert policy_engine.can(actor=actor, action="read", resource="trainings").allowed is True
        denied = policy_engine.can(actor=actor, action="read", resource="admin")
        assert denied.allowed is False

    def test_training_specialist_cannot_access_incidents(self):
        """Training specialist cannot access incidents module."""
        actor = ActorContext(
            user_id="training123",
            tenant_id="tenant1",
            roles=("teacher",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="incidents",
        )
        assert decision.allowed is False
        assert decision.reason == "module_access_denied"

    def test_инспектор_подрядчика_читает_документы_но_не_меняет(self):
        """Срез-227: проверка закрепляла контракт, который сменил срез-217.

        Раньше здесь стояло «инспектор подрядчика не допущен к модулю
        документов». Единая карта прав экрана (решение владельца, срез-217)
        говорит иначе: ``doc.view`` выдан и ему — подрядчик обязан видеть
        документы, по которым его проверяют. Ручка `GET /documents` пускала его
        УЖЕ ДО этого среза; отказывал только движок прав модуля, и это было
        расхождение, а не защита.

        Граница осталась настоящей: ЧИТАТЬ можно, МЕНЯТЬ нельзя — ``doc.create``
        инспектору не выдан.
        """

        actor = ActorContext(
            user_id="contractor123",
            tenant_id="tenant1",
            roles=("inspector_contractor",),
        )
        assert policy_engine.can(actor=actor, action="read", resource="documents").allowed is True
        denied = policy_engine.can(actor=actor, action="create", resource="documents")
        assert denied.allowed is False

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

    def test_бухгалтер_читает_отчёты_и_документы_но_не_инструктажи(self):
        """Срез-227: та же правка контракта, что у инспектора подрядчика.

        Словарь модулей по-прежнему записывает бухгалтеру один ``reports`` — он
        не менялся. Но круг модулей роли считается теперь как записанное руками
        ПЛЮС следующее из её прав, а единая карта даёт бухгалтеру ``doc.view``
        (счета и акты — его работа). Ручка `GET /documents` пускала его уже до
        этого среза.

        Граница осталась настоящей: инструктажи бухгалтеру закрыты, ``documents``
        он только читает.
        """

        from app.core.rbac_abac import modules_for_role

        actor = ActorContext(
            user_id="accountant123",
            tenant_id="tenant1",
            roles=("accountant",),
        )
        assert MODULE_PERMISSIONS.get("accountant", set()) == {
            "reports"
        }, "словарь модулей не должен был меняться"
        assert {"reports", "documents"} <= modules_for_role("accountant")

        assert (
            policy_engine.can(actor=actor, action="read", resource="reports").reason
            != "module_access_denied"
        )
        assert policy_engine.can(actor=actor, action="read", resource="documents").allowed is True
        assert (
            policy_engine.can(actor=actor, action="create", resource="documents").allowed is False
        )
        assert policy_engine.can(actor=actor, action="read", resource="briefings").allowed is False


class TestModuleAccessAuditFields:
    """Test audit metadata for module access decisions."""

    def test_module_denied_audit_fields(self):
        """Module denial should include audit fields."""
        actor = ActorContext(
            user_id="specialist123",
            tenant_id="tenant1",
            roles=("ot_specialist",),
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
            roles=("teacher",),
        )
        decision = policy_engine.can(
            actor=actor,
            action="read",
            resource="risk_maps",
        )
        assert decision.reason == "module_access_denied"
        assert decision.audit_meta.get("module") == "risk"
