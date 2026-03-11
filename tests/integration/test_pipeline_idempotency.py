from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_pipeline_runs_idempotency(async_client, make_auth_headers):
    profile_payload = {
        "code": "doc_basic_v1",
        "name": "Doc Basic",
        "steps": [
            {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
            {"code": "apply_headers", "required": True, "params_schema": "HeadersParamsV1"},
            {"code": "replace", "required": True, "params_schema": "ReplaceParamsV1"},
            {"code": "convert_pdf", "required": True, "params_schema": "PdfParamsV1"},
            {"code": "build_zip", "required": True, "params_schema": "ZipParamsV1"},
        ],
        "limits": {"max_parallel": 2, "max_parallel_per_step": {}},
        "is_active": True,
    }
    tenant_headers = {**dict(async_client.headers), **await make_auth_headers()}
    created = await async_client.post("/api/v1/pipelines/profiles", json=profile_payload, headers=tenant_headers)
    assert created.status_code == 201

    payload = {"profile_code": "doc_basic_v1", "inputs": {"template_version_id": "tv-1"}, "options": {}}
    headers = {**tenant_headers, "Idempotency-Key": "next28-k1"}
    first = await async_client.post("/api/v1/pipelines/runs", json=payload, headers=headers)
    second = await async_client.post("/api/v1/pipelines/runs", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]

    conflict = await async_client.post(
        "/api/v1/pipelines/runs",
        json={"profile_code": "doc_basic_v1", "inputs": {"template_version_id": "tv-2"}},
        headers=headers,
    )
    assert conflict.status_code == 409
