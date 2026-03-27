from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

router_module = importlib.import_module("app.api.v1.router")

_enforce_tenant_generation_quota = router_module._enforce_tenant_generation_quota


@pytest.mark.anyio
async def test_enforce_tenant_generation_quota_uses_canonical_assert_quota_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int, str]] = []

    async def fake_assert_quota(session, *, tenant, kind: str, delta: int) -> None:
        calls.append((kind, delta, tenant.id))

    monkeypatch.setattr(router_module, "assert_quota", fake_assert_quota)

    tenant = SimpleNamespace(id="tenant-123")
    session = object()

    await _enforce_tenant_generation_quota(session, tenant)

    assert calls == [
        ("jobs", 1, "tenant-123"),
        ("generations_month", 1, "tenant-123"),
    ]