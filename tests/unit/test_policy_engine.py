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
    assert decision.reason == "scope_mismatch"


def test_policy_engine_deny_auditor_write() -> None:
    decision = authorize(
        Subject(user_id="u1", tenant_id="t1", roles=("auditor_ro",)),
        action="update",
        resource=Resource(resource_type="documents"),
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"
