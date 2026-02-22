from __future__ import annotations

import pytest

from app.modules.pipelines.schemas import PipelineProfileCreate


def test_pipeline_profile_steps_validation() -> None:
    payload = PipelineProfileCreate(
        code="docpack_default",
        name="Default",
        steps=[
            {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
            {"code": "convert_pdf", "required": True, "params_schema": "PdfParamsV1"},
        ],
    )
    assert payload.steps[0].code == "render_docx"


@pytest.mark.anyio
async def test_pipeline_run_is_idempotent(client, tenant_headers):
    profile_payload = {
        "code": "default_docpack_v1",
        "name": "Default",
        "steps": [
            {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
            {"code": "convert_pdf", "required": True, "params_schema": "PdfParamsV1"},
        ],
        "limits": {"max_parallel": 2, "max_parallel_per_step": {}},
        "is_active": True,
    }
    created = await client.post("/api/v1/pipelines/profiles", json=profile_payload, headers=tenant_headers)
    assert created.status_code == 201

    run_payload = {"profile_code": "default_docpack_v1", "input": {"template_version_id": "tv-1"}}
    headers = {**tenant_headers, "Idempotency-Key": "idem-next23"}
    first = await client.post("/api/v1/pipelines/run", json=run_payload, headers=headers)
    second = await client.post("/api/v1/pipelines/run", json=run_payload, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
