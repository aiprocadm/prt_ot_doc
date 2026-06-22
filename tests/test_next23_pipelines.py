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
async def test_pipeline_run_is_idempotent(async_client, make_auth_headers):
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
    tenant_headers = {**dict(async_client.headers), **await make_auth_headers()}
    created = await async_client.post(
        "/api/v1/pipelines/profiles", json=profile_payload, headers=tenant_headers
    )
    assert created.status_code == 201

    run_payload = {"profile_code": "default_docpack_v1", "inputs": {"template_version_id": "tv-1"}}
    headers = {**tenant_headers, "Idempotency-Key": "idem-next23"}
    first = await async_client.post("/api/v1/pipelines/runs", json=run_payload, headers=headers)
    second = await async_client.post("/api/v1/pipelines/runs", json=run_payload, headers=headers)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]


@pytest.mark.anyio
async def test_pipeline_run_requires_x_tenant_header(async_client, make_auth_headers):
    profile_payload = {
        "code": "default_docpack_v2",
        "name": "Default",
        "steps": [
            {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
        ],
        "limits": {"max_parallel": 1, "max_parallel_per_step": {}},
        "is_active": True,
    }
    tenant_headers = {**dict(async_client.headers), **await make_auth_headers()}
    created = await async_client.post(
        "/api/v1/pipelines/profiles", json=profile_payload, headers=tenant_headers
    )
    assert created.status_code == 201

    run_payload = {"profile_code": "default_docpack_v2", "inputs": {"template_version_id": "tv-2"}}
    no_tenant_headers = {"Idempotency-Key": "idem-no-tenant"}
    resp = await async_client.post(
        "/api/v1/pipelines/run", json=run_payload, headers=no_tenant_headers
    )
    assert resp.status_code == 400
    assert "X-Tenant" in resp.text
