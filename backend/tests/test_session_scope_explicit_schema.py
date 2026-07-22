"""Pin tests for ``session_scope`` schema_name propagation (iter-17 RB-002b).

When ``DEFAULT_TENANT_SLUG`` happens to be the same slug as a tenant that
also owns a dedicated tenant schema (e.g. ``demo`` with ``tenant_demo``),
``AsyncSessionLocal`` short-circuits to the shared schema. That broke
``bootstrap_demo_tenant``: it created ``tenant_demo.training_course`` via
``aensure_tenant_schema`` and then opened a session that read from ``public``.

These tests pin the fix: ``session_scope`` must forward ``schema_name`` so
callers can override the short-circuit explicitly.
"""

from __future__ import annotations

import asyncio

import pytest

from app.db import session as session_module


class _FakeSession:
    """Minimal async-context shim that records nothing besides entry/exit."""

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def test_session_scope_forwards_schema_name(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_local(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(session_module, "AsyncSessionLocal", fake_local)

    async def run() -> None:
        async with session_module.session_scope(tenant="demo", schema_name="tenant_demo"):
            pass

    asyncio.run(run())

    assert captured == {"tenant": "demo", "schema_name": "tenant_demo", "rls_bypass": False}


def test_session_scope_defaults_schema_name_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_local(**kwargs):
        captured.update(kwargs)
        return _FakeSession()

    monkeypatch.setattr(session_module, "AsyncSessionLocal", fake_local)

    async def run() -> None:
        async with session_module.session_scope(tenant="public"):
            pass

    asyncio.run(run())

    assert captured == {"tenant": "public", "schema_name": None, "rls_bypass": False}
