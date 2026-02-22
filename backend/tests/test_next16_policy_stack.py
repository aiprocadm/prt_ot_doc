from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db.scoping import scope_query
from app.core.rbac_abac import ActorContext, policy_engine
from app.core.tenancy import require_tenant
from app.modules.audit.security_log import log_security_decision


class Base(DeclarativeBase):
    pass


class DemoResource(Base):
    __tablename__ = "demo_resource"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    site_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DummySession:
    def __init__(self) -> None:
        self.items = []

    def add(self, item):
        self.items.append(item)

    async def flush(self):
        return None


def test_require_tenant_missing_header_returns_400() -> None:
    request = SimpleNamespace(headers={}, state=SimpleNamespace(trace_id="trace-1"))
    with pytest.raises(HTTPException) as exc:
        require_tenant(request)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "tenant_required"


def test_policy_engine_abac_denies_foreign_site() -> None:
    actor = ActorContext(user_id="u1", tenant_id="t1", roles=("admin",), site_ids=("site-A",))
    decision = policy_engine.enforce(
        actor,
        action="read",
        resource="documents",
        ctx={"site_id": "site-B"},
    )
    # admins bypass ABAC, so use non-admin role for deny check
    if decision.allowed:
        actor = ActorContext(user_id="u1", tenant_id="t1", roles=("executor",), site_ids=("site-A",))
        decision = policy_engine.enforce(
            actor,
            action="read",
            resource="documents",
            ctx={"site_id": "site-B"},
        )
    assert decision.allowed is False
    assert decision.reason == "scope_mismatch"


def test_scope_query_always_applies_tenant_filter() -> None:
    stmt = scope_query(select(DemoResource), model=DemoResource, tenant_id="tenant-1")
    compiled = str(stmt)
    assert "demo_resource.tenant_id" in compiled


@pytest.mark.asyncio
async def test_security_audit_log_records_deny() -> None:
    session = DummySession()
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
        state=SimpleNamespace(trace_id="cid-1"),
    )
    entry = await log_security_decision(
        session=session,  # type: ignore[arg-type]
        request=request,  # type: ignore[arg-type]
        tenant_id="tenant-1",
        user_id="user-1",
        action="update",
        resource_type="document",
        resource_id="doc-1",
        decision="deny",
        reason_code="scope_mismatch",
    )
    assert entry.decision == "deny"
    assert entry.reason_code == "scope_mismatch"
    assert len(session.items) == 1
