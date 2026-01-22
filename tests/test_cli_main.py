from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import uuid

import pytest
import typer
from typer.testing import CliRunner

from app.cli.main import _extract_payload, _resolve_template, cli, load_context
from app.models.models import Template, TemplateVersion, TemplateVersionStatus


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_load_context_reads_json(tmp_path: Path) -> None:
    payload = {"foo": "bar", "nested": {"value": 42}}
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_context(path)

    assert loaded == payload


def test_extract_payload_prefers_nested_context() -> None:
    payload = {
        "context": {"name": "Alice"},
        "replacements": {"{{company}}": "Wonderland"},
        "header_text": "Header",
        "footer_text": "Footer",
        "output_basename": "document",
    }

    (
        context,
        replacements,
        header_text,
        footer_text,
        output_basename,
    ) = _extract_payload(payload)

    assert context == {"name": "Alice"}
    assert replacements == {"{{company}}": "Wonderland"}
    assert header_text == "Header"
    assert footer_text == "Footer"
    assert output_basename == "document"


def test_extract_payload_with_flat_data() -> None:
    payload = {"name": "Bob"}

    (
        context,
        replacements,
        header_text,
        footer_text,
        output_basename,
    ) = _extract_payload(payload)

    assert context == payload
    assert replacements is None
    assert header_text is None
    assert footer_text is None
    assert output_basename is None


@pytest.mark.anyio()
async def test_resolve_template_returns_active_version() -> None:
    template_id = "tpl-001"
    template = SimpleNamespace(id=template_id, tenant_id="tenant-x")
    version = SimpleNamespace(status=TemplateVersionStatus.ACTIVE, version=3)

    class DummyResult:
        def scalar_one_or_none(self) -> Any:
            return version

    class DummySession:
        async def get(self, model: type[Any], identity: Any) -> Any:
            if model is Template and identity == template_id:
                return template
            if model is TemplateVersion:
                return version
            raise AssertionError("Unexpected model request")

        async def execute(self, stmt: Any) -> DummyResult:  # noqa: ARG002 - statement unused
            return DummyResult()

    resolved_template, resolved_version = await _resolve_template(
        DummySession(), template_id
    )

    assert resolved_template is template
    assert resolved_version is version


@pytest.mark.anyio()
async def test_resolve_template_missing_template(capsys: pytest.CaptureFixture[str]) -> None:
    class DummySession:
        async def get(self, model: type[Any], identity: Any) -> None:  # noqa: ARG002
            return None

        async def execute(self, stmt: Any) -> None:  # noqa: ARG002
            pytest.fail("execute should not be called when template is missing")

    with pytest.raises(typer.Exit) as exc:
        await _resolve_template(DummySession(), "missing")

    assert exc.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Template missing not found" in captured.err


@pytest.mark.anyio()
async def test_resolve_template_without_active_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    template_id = "tpl-002"
    template = SimpleNamespace(id=template_id)

    class DummyResult:
        def scalar_one_or_none(self) -> None:
            return None

    class DummySession:
        async def get(self, model: type[Any], identity: Any) -> Any:
            if model is Template and identity == template_id:
                return template
            raise AssertionError("Unexpected model request")

        async def execute(self, stmt: Any) -> DummyResult:  # noqa: ARG002
            return DummyResult()

    with pytest.raises(typer.Exit) as exc:
        await _resolve_template(DummySession(), template_id)

    assert exc.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Template has no active version" in captured.err


def test_render_command_invokes_pipeline(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    payload = {
        "context": {"subject": "Letter"},
        "replacements": {"{{name}}": "Alice"},
        "header_text": "Header",
        "footer_text": "Footer",
        "idempotency_key": "idem-123",
        "output_basename": "letter",
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    template = SimpleNamespace(id="tpl-01", tenant_id="tenant-override")
    version = SimpleNamespace(id="ver-01")

    async def fake_resolve(session: Any, template_id: str) -> tuple[Any, Any]:  # noqa: ARG001
        assert template_id == "tpl-01"
        return template, version

    monkeypatch.setattr("app.cli.main._resolve_template", fake_resolve)

    service_calls: list[dict[str, Any]] = []

    class FakePipelineService:
        async def run(self, **kwargs: Any) -> Any:
            service_calls.append(kwargs)
            return SimpleNamespace(
                id="run-001",
                status=SimpleNamespace(value="done"),
                outputs={"doc": "templates/letter.docx"},
                result_metadata={"duration": 1.23},
            )

    fake_session_records: list[Any] = []

    @asynccontextmanager
    async def fake_session_factory(*, tenant: str | None = None):
        session = SimpleNamespace(tenant=tenant)
        fake_session_records.append(session)
        yield session

    monkeypatch.setattr("app.cli.main.AsyncSessionLocal", lambda tenant=None: fake_session_factory(tenant=tenant))
    monkeypatch.setattr("app.cli.main.PipelineService", lambda: FakePipelineService())

    result = runner.invoke(
        cli,
        ["render", "tpl-01", str(payload_path), "--tenant", "explicit-tenant"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "id": "run-001",
        "status": "done",
        "outputs": {"doc": "templates/letter.docx"},
        "result_metadata": {"duration": 1.23},
    }
    assert len(service_calls) == 1
    call = service_calls[0]
    assert call["session"] is fake_session_records[0]
    assert call["context"] == {"subject": "Letter"}
    assert call["replacements"] == {"{{name}}": "Alice"}
    assert call["header_text"] == "Header"
    assert call["footer_text"] == "Footer"
    assert call["idempotency_key"] == "idem-123"
    assert call["output_basename"] == "letter"
    assert call["tenant_id"] == "explicit-tenant"
    assert fake_session_records[0].tenant == "explicit-tenant"


def test_pipeline_command_enqueues_task(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    payload = {
        "context": {"value": 7},
        "idempotency_key": "existing-key",
    }
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")

    template = SimpleNamespace(id="tpl-02", tenant_id="tenant-123")
    version = SimpleNamespace(id="ver-02")
    run = SimpleNamespace(id="run-xyz", tenant_id="tenant-123")

    async def fake_resolve(session: Any, template_id: str) -> tuple[Any, Any]:  # noqa: ARG001
        assert template_id == "tpl-02"
        return template, version

    class FakePipelineService:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def ensure_pending_run(self, session: Any, **kwargs: Any) -> tuple[Any, bool]:
            self.calls.append({"session": session, **kwargs})
            return run, True

    fake_service = FakePipelineService()
    sessions: list[Any] = []

    class FakeSession(SimpleNamespace):
        def __init__(self, *, tenant: str | None) -> None:
            super().__init__(tenant=tenant)
            self.commit_calls = 0
            self.refresh_targets: list[Any] = []

        async def commit(self) -> None:
            self.commit_calls += 1

        async def refresh(self, target: Any) -> None:
            self.refresh_targets.append(target)

    @asynccontextmanager
    async def fake_session_factory(*, tenant: str | None = None):
        session = FakeSession(tenant=tenant)
        sessions.append(session)
        yield session

    calls: list[dict[str, Any]] = []

    class FakeTask(SimpleNamespace):
        pass

    def fake_apply_async(*, args: list[Any], task_id: str, headers: dict[str, str]) -> Any:
        calls.append({"args": args, "task_id": task_id, "headers": headers})
        return FakeTask(id="celery-123")

    monkeypatch.setattr("app.cli.main._resolve_template", fake_resolve)
    monkeypatch.setattr("app.cli.main.PipelineService", lambda: fake_service)
    monkeypatch.setattr(
        "app.cli.main.AsyncSessionLocal", lambda tenant=None: fake_session_factory(tenant=tenant)
    )
    monkeypatch.setattr("app.cli.main.run_pipeline_task.apply_async", fake_apply_async)
    monkeypatch.setattr("app.cli.main.uuid.uuid4", lambda: uuid.UUID(int=1))

    result = runner.invoke(cli, ["pipeline", "tpl-02", str(payload_path)])

    assert result.exit_code == 0
    assert "Enqueued pipeline run run-xyz as task celery-123" in result.stdout
    assert len(fake_service.calls) == 1
    call = fake_service.calls[0]
    assert call["session"] is sessions[0]
    assert call["context"] == {"value": 7}
    assert call["replacements"] is None
    assert call["tenant_id"] == "tenant-123"
    assert call["idempotency_key"] == "existing-key"
    assert sessions[0].tenant is None
    assert sessions[0].commit_calls == 1
    assert sessions[0].refresh_targets == [run]
    assert calls == [
        {
            "args": ["run-xyz", "tenant-123"],
            "task_id": "run-xyz",
            "headers": {"trace_id": "00000000-0000-0000-0000-000000000001"},
        }
    ]


def test_header_command_outputs_storage_key(runner: CliRunner) -> None:
    result = runner.invoke(cli, ["header", "example"])

    assert result.exit_code == 0
    assert "Template key: templates/example.docx" in result.stdout


def test_replace_command_updates_document(monkeypatch: pytest.MonkeyPatch, runner: CliRunner, tmp_path: Path) -> None:
    class FakeStorage:
        def __init__(self) -> None:
            self.data = b"Hello, {{name}}!"

        def get(self, key: str) -> bytes:
            assert key == "templates/sample.docx"
            return self.data

    storage = FakeStorage()
    monkeypatch.setattr("app.cli.main.FileStorageService.default", lambda: storage)

    output_path = tmp_path / "result.docx"

    result = runner.invoke(
        cli,
        [
            "replace",
            "sample",
            "{{name}}",
            "Bob",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    assert output_path.read_bytes() == b"Hello, Bob!"
    assert "Written updated template" in result.stdout
