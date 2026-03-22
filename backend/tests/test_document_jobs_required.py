from app.api.v1.route_groups import ROUTER_GROUP_ORDER, ROUTER_GROUPS, describe_router_groups
from app.celery.tasks.document_jobs_required import (
    build_zip_job,
    index_file_content_job,
    render_docx_job,
    send_edo_job,
    verify_signature_job,
)


def test_document_job_wrappers_expose_compatibility_bridge_metadata() -> None:
    accepted = render_docx_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-1")
    indexed = index_file_content_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-2")
    deferred = send_edo_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-3")
    signature = verify_signature_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-4")
    zipped = build_zip_job(tenant_slug="tenant-a", job_id="job-1", step_id="step-5")

    assert accepted["status"] == "accepted"
    assert accepted["bridge_mode"] == "compatibility-wrapper"
    assert accepted["orchestrator"] == "document_pipeline_orchestrator"
    assert indexed["step_key"] == "index_file_content"
    assert zipped["step_key"] == "build_zip"
    assert deferred["deferred"] is True
    assert deferred["handler"] == "edo_orchestrator_bridge_pending"
    assert "canonical EDO pipeline jobs" in str(deferred["detail"])
    assert signature["deferred"] is True
    assert signature["handler"] == "signature_orchestrator_bridge_pending"


def test_route_group_description_matches_declared_group_order() -> None:
    described = describe_router_groups()

    assert tuple(described) == ROUTER_GROUP_ORDER
    assert len(described["document_core"]) == len(ROUTER_GROUPS["document_core"])
    assert any(item["prefix"] == "/documents" for item in described["document_core"])
    assert any("tasks" in item["tags"] for item in described["operations"])
