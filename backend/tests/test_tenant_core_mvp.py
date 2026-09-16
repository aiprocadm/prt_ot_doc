from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.db.scoping import scope_query
from app.core.rbac_abac import ActorContext, policy_engine
from app.db import session as db_session
from app.middleware.tenant import TenantMiddleware
from app.modules.tenancy.context import TenantContext, reset_tenant_context, set_tenant_context


class Base(DeclarativeBase):
    pass


class ScopedDemo(Base):
    __tablename__ = "scoped_demo"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    deleted_at: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DummySession:
    def __init__(self) -> None:
        self.info = {"search_path": ["tenant_a", "public"]}
        self.calls: list[str] = []
        self.params: list[dict | None] = []

    async def execute(self, stmt, params=None):
        # Срез-210: метка сессии уходит ПАРАМЕТРОМ (`set_config`), а не склейкой,
        # поэтому у запроса появился второй довод. Заглушка обязана повторять
        # боевой вызов, иначе проверка мерит не тот контракт.
        self.calls.append(str(stmt))
        self.params.append(params)
        return None


def test_tenant_middleware_requires_tenant_header() -> None:
    exc = TenantMiddleware._error(
        400, "corr-1", code="TENANT_REQUIRED", message="X-Tenant header required"
    )
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 400
    assert exc.detail["code"] == "TENANT_REQUIRED"


def test_scope_query_includes_tenant_and_soft_delete_filter() -> None:
    stmt = scope_query(select(ScopedDemo), model=ScopedDemo, tenant_id="tenant-a")
    compiled = str(stmt)
    assert "scoped_demo.tenant_id" in compiled
    assert "scoped_demo.deleted_at IS NULL" in compiled


@pytest.mark.asyncio
async def test_search_path_set_local_with_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = DummySession()
    monkeypatch.setattr(db_session, "_SUPPORTS_SCHEMAS", True)
    monkeypatch.setattr(db_session, "_SEARCH_PATH_SUPPORTED", True)

    ctx = TenantContext(
        tenant_id="t1",
        slug="tenant-a",
        schema="tenant_a",
        tenant_level="customer",
        s3_prefix="t1",
        plan="pro",
        correlation_id="cid-1",
    )
    token = set_tenant_context(ctx)
    try:
        await db_session._apply_search_path(dummy)  # type: ignore[arg-type]
    finally:
        reset_tenant_context(token)

    assert any("SET LOCAL search_path" in call for call in dummy.calls)
    # Метка сессии ставится через `set_config` с ПАРАМЕТРОМ: значение из
    # заголовка запроса больше не становится текстом SQL (разд. 64.1, срез-210).
    assert any("set_config('application_name'" in call for call in dummy.calls)
    assert {"value": "api:cid-1"} in dummy.params


def test_policy_engine_matrix_smoke() -> None:
    admin = ActorContext(user_id="u1", tenant_id="t1", roles=("admin",))
    viewer = ActorContext(user_id="u2", tenant_id="t1", roles=("executor",), site_ids=("site-a",))

    allow = policy_engine.enforce(
        admin, action="approve", resource="documents", ctx={"site_id": "site-x"}
    )
    deny = policy_engine.enforce(
        viewer, action="read", resource="documents", ctx={"site_id": "site-z"}
    )

    assert allow.allowed is True
    assert deny.allowed is False
