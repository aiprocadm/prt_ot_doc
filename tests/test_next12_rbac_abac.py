from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.core.rbac_abac import actor_from_claims, policy_engine, scoped_query
from app.models.models import Company, Incident
from sqlalchemy import select


def _actor(
    *,
    roles: list[str],
    company_ids: list[str] | None = None,
    project_ids: list[str] | None = None,
    contractor_ids: list[str] | None = None,
    allowed_statuses: list[str] | None = None,
    max_risk_level: int | None = None,
):
    return actor_from_claims(
        {
            "sub": str(uuid4()),
            "tenant_id": str(uuid4()),
            "company_ids": company_ids or [],
            "project_ids": project_ids or [],
            "contractor_ids": contractor_ids or [],
            "allowed_statuses": allowed_statuses or [],
            "max_risk_level": max_risk_level,
        },
        roles,
    )


def test_owner_can_do_everything_in_tenant() -> None:
    actor = _actor(roles=["owner"])
    for action in ("read", "create", "update", "delete", "approve", "sign", "export"):
        decision = policy_engine.can(actor, action=action, resource="documents")
        assert decision.allowed is True


def test_auditor_ro_cannot_create_or_update() -> None:
    actor = _actor(roles=["auditor_ro"])
    assert policy_engine.can(actor, action="create", resource="incidents").allowed is False
    assert policy_engine.can(actor, action="update", resource="inspections").allowed is False


def test_executor_cannot_access_other_project() -> None:
    actor = _actor(roles=["executor"], project_ids=["proj-1"])
    allowed = policy_engine.can(
        actor, action="read", resource="documents", obj=SimpleNamespace(project_id="proj-1")
    )
    denied = policy_engine.can(
        actor, action="read", resource="documents", obj=SimpleNamespace(project_id="proj-2")
    )
    assert allowed.allowed is True
    assert denied.allowed is False


def test_risk_level_ceiling_blocks_high_risk_doc() -> None:
    actor = _actor(roles=["hse_specialist"], max_risk_level=2)
    decision = policy_engine.can(actor, action="read", resource="documents", ctx={"risk_level": 3})
    assert decision.allowed is False


def test_status_filter_blocks_unapproved() -> None:
    actor = _actor(roles=["executor"], allowed_statuses=["approved"])
    decision = policy_engine.can(
        actor, action="read", resource="documents", ctx={"status": "draft"}
    )
    assert decision.allowed is False


def test_scoped_query_always_applies_filters() -> None:
    actor = _actor(
        roles=["executor"], company_ids=["cmp-1"], allowed_statuses=["approved"], max_risk_level=2
    )
    stmt = scoped_query(select(Incident), model=Incident, actor=actor, resource="incidents")
    compiled = str(stmt)
    assert "company_id" in compiled
    assert "status" in compiled

    company_stmt = scoped_query(
        select(Company).where(Company.id == "cmp-2"),
        model=Company,
        actor=actor,
        resource="companies",
    )
    company_compiled = str(company_stmt)
    assert "company.id" in company_compiled
