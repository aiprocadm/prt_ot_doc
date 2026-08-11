from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.models import AuthzPolicy
from app.modules.rbac_abac.engine import _match_condition, evaluate
from app.modules.rbac_abac.types import PolicyContext, Resource, Subject
from app.services.audit import field_level_diff


def test_policy_engine_deny_by_default_without_permission() -> None:
    subject = Subject(user_id="u1", tenant_id="t1", roles=("executor",), permissions=())
    decision = evaluate(subject, "read", Resource(resource_type="documents", attrs={}))
    assert decision.allow is False
    assert decision.reason == "missing_permission"


def test_policy_engine_allow_with_permission_and_abac_policy() -> None:
    subject = Subject(
        user_id="u1",
        tenant_id="t1",
        roles=("executor",),
        permissions=("documents:read",),
        company_ids=("c1",),
    )
    policy = AuthzPolicy(
        id="p-1",
        tenant_id="t1",
        resource="documents",
        action="read",
        effect="allow",
        conditions_json={"all": [{"attr": "company_id", "op": "in", "value": "$scope.company_ids"}]},
        priority=10,
        enabled=True,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        version=1,
    )
    decision = evaluate(
        subject,
        "read",
        Resource(resource_type="documents", attrs={"company_id": "c1"}),
        PolicyContext(tenant_id="t1", abac_scopes={"company_ids": ["c1"]}, request_attrs={"policies": [policy]}),
    )
    assert decision.allow is True
    assert decision.matched_policy_id == "p-1"


def test_deny_overrides_allow_same_priority() -> None:
    subject = Subject(
        user_id="u1",
        tenant_id="t1",
        roles=("executor",),
        permissions=("documents:read",),
        company_ids=("c1",),
    )
    allow_policy = AuthzPolicy(
        id="p-allow",
        tenant_id="t1",
        resource="documents",
        action="read",
        effect="allow",
        conditions_json={"all": [{"attr": "company_id", "op": "eq", "value": "c1"}]},
        priority=10,
        enabled=True,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        version=1,
    )
    deny_policy = AuthzPolicy(
        id="p-deny",
        tenant_id="t1",
        resource="documents",
        action="read",
        effect="deny",
        conditions_json={"all": [{"attr": "status", "op": "eq", "value": "archived"}]},
        priority=10,
        enabled=True,
        created_at=datetime.now(tz=timezone.utc),
        updated_at=datetime.now(tz=timezone.utc),
        version=1,
    )
    decision = evaluate(
        subject,
        "read",
        Resource(resource_type="documents", attrs={"company_id": "c1", "status": "archived"}),
        PolicyContext(tenant_id="t1", abac_scopes={"company_ids": ["c1"]}, request_attrs={"policies": [allow_policy, deny_policy]}),
    )
    assert decision.allow is False
    assert decision.reason == "policy_deny"


@pytest.mark.parametrize(
    "op,left,right,expected",
    [
        ("eq", "a", "a", True),
        ("ne", "a", "b", True),
        ("in", "a", ["a", "b"], True),
        ("not_in", "c", ["a", "b"], True),
        ("lt", 1, 2, True),
        ("lte", 2, 2, True),
        ("gt", 3, 2, True),
        ("gte", 2, 2, True),
        ("contains", ["a", "b"], "a", True),
        ("exists", "x", None, True),
        ("not_exists", None, None, True),
    ],
)
def test_condition_ops(op: str, left, right, expected: bool) -> None:
    cond = {"attr": "k", "op": op, "value": right}
    assert _match_condition(cond, {"k": left}, {}) is expected


def test_field_level_diff_nested_and_masking() -> None:
    before = {"profile": {"email": "a@x.com", "name": "A"}, "items": [{"id": "1", "v": 1}]}
    after = {"profile": {"email": "b@x.com", "name": "B"}, "items": [{"id": "1", "v": 2}, {"id": "2", "v": 3}]}
    diff = field_level_diff(before, after)
    assert "profile.email" in diff["fields"]
    assert diff["fields"]["profile.email"]["to"].endswith("@x.com")
    assert "items" in diff["collections"]
    assert diff["collections"]["items"]["added"]
