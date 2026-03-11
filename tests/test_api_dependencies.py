from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import dependencies


@pytest.fixture(autouse=True)
def _clear_file_storage_cache() -> None:
    dependencies.get_file_storage_service.cache_clear()
    yield
    dependencies.get_file_storage_service.cache_clear()


def test_get_file_storage_service_returns_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"ensure_ready": 0}

    class DummyStorage:
        def ensure_ready(self) -> None:
            calls["ensure_ready"] += 1

    storage = DummyStorage()
    monkeypatch.setattr(
        dependencies.FileStorageService,
        "default",
        classmethod(lambda cls: storage),
    )

    first = dependencies.get_file_storage_service()
    second = dependencies.get_file_storage_service()

    assert first is storage
    assert second is storage
    assert calls["ensure_ready"] == 1


@pytest.mark.anyio
async def test_get_session_uses_tenant_session_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyContextManager:
        def __init__(self) -> None:
            self.session = object()
            self.exited = False

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            self.exited = True

    class Recorder:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []
            self.contexts: list[DummyContextManager] = []

        def __call__(self, *, tenant: str, schema_name: str | None = None):
            ctx = DummyContextManager()
            self.calls.append((tenant, schema_name))
            self.contexts.append(ctx)
            return ctx

    recorder = Recorder()
    monkeypatch.setattr(dependencies, "get_tenant_session", recorder)

    tenant = SimpleNamespace(slug="acme", schema_name="tenant_acme", id="tenant-id")
    generator = dependencies.get_session(tenant)

    session = await generator.__anext__()
    assert session is recorder.contexts[0].session
    assert recorder.calls == [("acme", "tenant_acme")]

    await generator.aclose()
    assert recorder.contexts[0].exited is True
