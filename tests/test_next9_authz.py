from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.rbac_abac import (
    ROLE_PERMISSIONS,
    ActorContext,
    actor_from_claims,
    audit_authz_decision,
    policy_engine,
    scoped_query,
)
from app.models.models import AuditLog, Incident, Template


def _actor(
    *,
    roles: list[str],
    company_ids: list[str] | None = None,
    contractor_ids: list[str] | None = None,
) -> ActorContext:
    claims = {
        "sub": str(uuid4()),
        "tenant_id": str(uuid4()),
        "company_ids": company_ids or [],
        "contractor_ids": contractor_ids or [],
    }
    return actor_from_claims(claims, roles)


def test_owner_can_list_documents_across_scope() -> None:
    actor = _actor(roles=["owner"])
    decision = policy_engine.authorize(actor, action="list", resource="documents")
    assert decision.allowed is True


def test_hse_specialist_denied_on_foreign_company() -> None:
    actor = _actor(roles=["hse_specialist"], company_ids=["cmp-1"])
    obj = SimpleNamespace(company_id="cmp-2")
    decision = policy_engine.authorize(actor, action="read", resource="documents", obj=obj)
    assert decision.allowed is False
    assert decision.reason == "scope_mismatch"


def test_auditor_cannot_update_incident() -> None:
    actor = _actor(roles=["auditor_ro"])
    decision = policy_engine.authorize(actor, action="update", resource="incidents")
    assert decision.allowed is False


def test_client_cannot_access_templates() -> None:
    actor = _actor(roles=["client"])
    decision = policy_engine.authorize(actor, action="read", resource="templates")
    assert decision.allowed is False
    # client has no "templates" module (MODULE_PERMISSIONS["client"]), so the
    # module gate denies first — module_access_denied is the correct reason.
    assert decision.reason in {"module_access_denied", "client_resource_restricted", "missing_permission"}


def test_inspector_contractor_reads_within_contractor() -> None:
    actor = _actor(roles=["inspector_contractor"], contractor_ids=["ctr-1"])
    allowed = policy_engine.authorize(
        actor,
        action="read",
        resource="inspections",
        obj=SimpleNamespace(contractor_id="ctr-1"),
    )
    denied = policy_engine.authorize(
        actor,
        action="read",
        resource="inspections",
        obj=SimpleNamespace(contractor_id="ctr-2"),
    )
    assert allowed.allowed is True
    assert denied.allowed is False


def test_scoped_query_filters_company_rows() -> None:
    actor = _actor(roles=["hse_specialist"], company_ids=["cmp-1"])
    stmt = scoped_query(select(Incident), model=Incident, actor=actor, resource="incidents")
    compiled = str(stmt)
    assert "company_id" in compiled


def test_scoped_query_fail_closed_for_scoped_resource_without_columns() -> None:
    actor = _actor(roles=["hse_specialist"], company_ids=["cmp-1"])
    with pytest.raises(Exception):
        scoped_query(select(Template), model=Template, actor=actor, resource="templates")


def test_missing_permission_returns_forbidden_decision() -> None:
    # student has the "training" module but no trainings:delete permission, so this
    # passes the module gate and is denied at the permission layer. (resource=
    # "documents" would deny earlier as module_access_denied — student has no
    # documents module.)
    actor = _actor(roles=["student"])
    decision = policy_engine.authorize(actor, action="delete", resource="trainings")
    assert decision.allowed is False
    assert decision.reason == "missing_permission"


def test_role_mapping_contains_required_next9_roles() -> None:
    for role in [
        "owner",
        "admin",
        "methodist",
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
        "lawyer",
        "line_manager",
        "client",
        "auditor_ro",
        "inspector_contractor",
    ]:
        assert role in ROLE_PERMISSIONS


@pytest.mark.anyio("asyncio")
async def test_deny_write_produces_authz_audit_event(sessionmaker) -> None:
    actor = _actor(roles=["auditor_ro"])
    decision = policy_engine.authorize(actor, action="update", resource="incidents")
    assert decision.allowed is False

    async with sessionmaker() as session:
        session.info["tenant"] = "test"
        request = SimpleNamespace(
            url=SimpleNamespace(path="/api/v1/incidents/1"),
            client=SimpleNamespace(host="127.0.0.1"),
        )
        await audit_authz_decision(
            session=session,
            request=request,
            actor=actor,
            resource="incidents",
            action="update",
            decision=decision,
            object_id="1",
        )
        await session.commit()

        rows = (
            (await session.execute(select(AuditLog).where(AuditLog.action == "authz_decision")))
            .scalars()
            .all()
        )
        assert rows
        assert rows[-1].details.get("allowed") is False
