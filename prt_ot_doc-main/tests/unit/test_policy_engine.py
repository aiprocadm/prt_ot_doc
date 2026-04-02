from app.modules.rbac_abac.engine import authorize
from app.modules.rbac_abac.types import Resource, Subject


def test_policy_engine_allow_admin_documents_update() -> None:
    decision = authorize(
        Subject(user_id="u1", tenant_id="t1", roles=("admin",), company_ids=("c1",)),
        action="update",
        resource=Resource(resource_type="documents", attrs={"company_id": "c1"}),
    )
    assert decision.allow is True


def test_policy_engine_deny_scope_mismatch() -> None:
    decision = authorize(
        Subject(user_id="u1", tenant_id="t1", roles=("auditor_ro",), company_ids=("c1",)),
        action="read",
        resource=Resource(resource_type="documents", attrs={"company_id": "c2"}),
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"


def test_policy_engine_deny_permission_mismatch() -> None:
    decision = authorize(
        Subject(
            user_id="u1",
            tenant_id="t1",
            roles=("project_manager",),
            permissions=("documents.read",),
            company_ids=("c1",),
        ),
        action="generate",
        resource=Resource(resource_type="documents", attrs={"company_id": "c1"}),
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"


def test_policy_engine_deny_project_scope_mismatch() -> None:
    decision = authorize(
        Subject(user_id="u1", tenant_id="t1", roles=("project_manager",), project_ids=("p1",)),
        action="read",
        resource=Resource(resource_type="documents", attrs={"project_id": "p2"}),
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"


def test_policy_engine_deny_risk_level_above_max() -> None:
    decision = authorize(
        Subject(user_id="u1", tenant_id="t1", roles=("hse_specialist",), risk_level_max=2),
        action="read",
        resource=Resource(resource_type="risk_maps", attrs={"risk_level": "high"}),
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"
