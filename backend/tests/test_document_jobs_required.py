from __future__ import annotations

from app.api.v1.route_groups import ROUTER_GROUP_ORDER, ROUTER_GROUPS, describe_router_groups
from app.celery.tasks import document_jobs_required as module
from app.celery.tasks.document_jobs_required import (
    build_zip_job,
    export_report_job,
    index_file_content_job,
    render_docx_job,
    send_edo_job,
    sync_integration_job,
    verify_signature_job,
)


def test_document_job_wrappers_delegate_to_runtime_bridge(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str]] = []

    def fake_runner(*, tenant_slug: str, job_id: str, step_id: str, step_key: str):
        calls.append((tenant_slug, job_id, step_id, step_key))
        return module._job_step_response(
            tenant_slug=tenant_slug,
            job_id=job_id,
            step_id=step_id,
            step_key=step_key,
            status="completed",
            step_status="success",
        )

    monkeypatch.setattr(module, "_run_coroutine_step", fake_runner)

    responses = [
        render_docx_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-1"),
        verify_signature_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-2"),
        send_edo_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-3"),
        build_zip_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-4"),
        index_file_content_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-5"),
    ]

    assert [call[3] for call in calls] == [
        "render_docx",
        "verify_signature",
        "send_edo",
        "build_zip",
        "index_file_content",
    ]
    for response in responses:
        assert response["status"] == "completed"
        assert response["bridge_mode"] == "compatibility-execution-bridge"
        assert response["orchestrator"] == "document_pipeline_orchestrator"
        assert response["step_status"] == "success"


def test_document_job_wrappers_keep_backward_compatible_envelope_when_no_bridge_registered() -> None:
    module._COMPATIBILITY_BRIDGES.clear()

    report = export_report_job(tenant_slug="tenant-a", report_id="report-1")
    sync = sync_integration_job(tenant_slug="tenant-a", integration_key="1c")

    assert report["status"] == "accepted"
    assert report["bridge_mode"] == "compatibility-wrapper"
    assert report["deferred"] is True
    assert sync["status"] == "accepted"
    assert sync["bridge_mode"] == "compatibility-wrapper"
    assert sync["deferred"] is True


def test_document_job_named_bridges_execute_runtime_handler(monkeypatch) -> None:
    captured: list[tuple[str, str]] = []

    async def fake_export(*, tenant_slug: str, report_id: str):
        captured.append((tenant_slug, report_id))
        return {"status": "exported", "artifact_id": f"artifact:{report_id}"}

    monkeypatch.setitem(module._COMPATIBILITY_BRIDGES, "export_report", fake_export)

    monkeypatch.setattr(module, "tenant_context", lambda tenant_slug: __import__('contextlib').nullcontext())
    monkeypatch.setattr(module, "ensure_tenant_schema", lambda tenant_slug: None)

    def fake_run(coro):
        import asyncio
        return asyncio.run(coro)

    import types
    monkeypatch.setitem(__import__('sys').modules, 'app.tasks', types.SimpleNamespace(_run_coroutine=fake_run))

    response = export_report_job(tenant_slug="tenant-a", report_id="report-42")

    assert captured == [("tenant-a", "report-42")]
    assert response["status"] == "exported"
    assert response["bridge_mode"] == "compatibility-execution-bridge"
    assert response["deferred"] is False
    assert response["artifact_id"] == "artifact:report-42"


def test_route_group_description_matches_declared_group_order() -> None:
    described = describe_router_groups()

    assert tuple(described) == ROUTER_GROUP_ORDER
    assert len(described["document_core"]) == len(ROUTER_GROUPS["document_core"])
    assert any(item["prefix"] == "/documents" for item in described["document_core"])
    assert any("tasks" in item["tags"] for item in described["operations"])
