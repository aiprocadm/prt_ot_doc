from __future__ import annotations

from app.core.rbac_abac import ActorContext, policy_engine
from app.modules.rbac_abac.engine import evaluate
from app.modules.rbac_abac.types import Resource, Subject


def test_contractors_cross_contractor_scope_is_denied() -> None:
    actor = ActorContext(
        user_id="u-1",
        tenant_id="t-1",
        # Срез-228: роль звалась ``hse_head`` — такой в продукте нет, и отказ
        # приходил раньше проверки области, то есть проверялось не то.
        roles=("ot_pb_lead",),
        contractor_ids=("ctr-1",),
    )
    decision = policy_engine.can(
        actor=actor,
        action="read",
        resource="contractors",
        ctx={"contractor_id": "ctr-2"},
    )
    assert decision.allowed is False
    assert decision.reason == "scope_mismatch"


def test_contractors_low_privilege_direct_api_denied_without_permission() -> None:
    subject = Subject(
        user_id="u-low",
        tenant_id="t-1",
        roles=("student",),
        permissions=(),
        contractor_ids=("ctr-1",),
    )
    decision = evaluate(
        subject, "read", Resource(resource_type="contractors", attrs={"contractor_id": "ctr-1"})
    )
    assert decision.allow is False
    assert decision.reason == "missing_permission"
