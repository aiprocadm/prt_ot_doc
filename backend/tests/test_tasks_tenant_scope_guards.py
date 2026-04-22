from __future__ import annotations

import asyncio

import pytest

from app.tasks._core import _resolve_task_tenant_scope


class _ScalarResult:
    def __init__(self, value: str | None) -> None:
        self._value = value

    def scalar_one_or_none(self) -> str | None:
        return self._value


class _FakeSession:
    def __init__(self, *, tenant_id: str | None, resolved_tenant_id: str | None) -> None:
        self.info = {"tenant_id": tenant_id}
        self._resolved_tenant_id = resolved_tenant_id

    async def execute(self, _stmt):  # noqa: ANN001
        return _ScalarResult(self._resolved_tenant_id)


def test_resolve_task_tenant_scope_uses_resolved_tenant_when_session_missing() -> None:
    session = _FakeSession(tenant_id=None, resolved_tenant_id="tenant-1")

    tenant_id, tenant_scope = asyncio.run(_resolve_task_tenant_scope(session, "tenant-slug"))

    assert tenant_id == "tenant-1"
    assert tenant_scope == ("tenant-1", "tenant-slug")


def test_resolve_task_tenant_scope_rejects_mismatch_between_session_and_worker_tenant() -> None:
    session = _FakeSession(tenant_id="tenant-a", resolved_tenant_id="tenant-b")

    with pytest.raises(ValueError, match="Tenant scope mismatch"):
        asyncio.run(_resolve_task_tenant_scope(session, "tenant-slug"))
