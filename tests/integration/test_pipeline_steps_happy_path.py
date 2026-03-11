from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_pipeline_run_happy_path_and_actions(async_client, make_auth_headers):
    profile_payload = {
        "code": "doc_happy_v1",
        "name": "Doc Happy",
        "steps": [
            {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
            {"code": "convert_pdf", "required": True, "params_schema": "PdfParamsV1"},
            {"code": "build_zip", "required": True, "params_schema": "ZipParamsV1"},
        ],
        "limits": {"max_parallel": 2, "max_parallel_per_step": {}},
        "is_active": True,
    }
    tenant_headers = {**dict(async_client.headers), **await make_auth_headers()}
    created = await async_client.post("/api/v1/pipelines/profiles", json=profile_payload, headers=tenant_headers)
    assert created.status_code == 201

    run = await async_client.post(
        "/api/v1/pipelines/runs",
        json={"profile_code": "doc_happy_v1", "inputs": {"template_version_id": "tv-1"}},
        headers={**tenant_headers, "Idempotency-Key": "next28-happy"},
    )
    assert run.status_code == 202
    run_id = run.json()["run_id"]

    details = await async_client.get(f"/api/v1/pipelines/runs/{run_id}", headers=tenant_headers)
    assert details.status_code == 200
    assert details.json()["run_id"] == run_id
    assert isinstance(details.json()["step_runs"], list)

    canceled = await async_client.post(f"/api/v1/pipelines/runs/{run_id}:cancel", headers=tenant_headers)
    assert canceled.status_code == 200
    assert canceled.json()["status"] == "canceled"
