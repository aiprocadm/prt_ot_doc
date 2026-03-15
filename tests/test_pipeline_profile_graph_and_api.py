from __future__ import annotations

import pytest

from app.modules.pipelines.graph import PipelineGraph, PipelineProfileValidator, safe_eval_condition


def test_graph_validator_requires_branch_default() -> None:
    graph = PipelineGraph(
        nodes=[
            {"id": "start", "type": "render_docx", "config": {"template_code": "tpl"}},
            {"id": "decision", "type": "branch"},
            {"id": "done", "type": "convert_pdf"},
        ],
        edges=[
            {"from": "start", "to": "decision"},
            {"from": "decision", "to": "done", "condition": "ctx.get('replace_map_id') != None"},
        ],
    )
    with pytest.raises(ValueError, match="must have at least 2 outgoing edges"):
        PipelineProfileValidator().validate(graph)


def test_safe_eval_condition_whitelist() -> None:
    assert safe_eval_condition("ctx.get('count', 0) >= 2 and 'pdf' in ctx.get('artifacts', [])", {"count": 2, "artifacts": ["docx", "pdf"]}) is True
    with pytest.raises(ValueError, match="unsafe"):
        safe_eval_condition("__import__('os').system('echo hacked')", {})


@pytest.mark.anyio
async def test_pipeline_profile_put_activate_and_runs_filters(async_client, make_auth_headers):
    tenant_headers = await make_auth_headers()
    client = async_client
    created = await client.post(
        "/api/v1/pipelines/profiles",
        headers=tenant_headers,
        json={
            "code": "builder-profile-v2",
            "name": "Builder Profile",
            "graph": {
                "nodes": [
                    {"id": "render", "type": "render_docx", "config": {"template_code": "builder-profile-v2"}},
                    {"id": "pdf", "type": "convert_pdf"},
                ],
                "edges": [{"from": "render", "to": "pdf"}],
            },
        },
    )
    assert created.status_code == 201
    profile_id = created.json()["id"]

    updated = await client.put(
        f"/api/v1/pipelines/profiles/{profile_id}",
        headers=tenant_headers,
        json={"name": "Builder Profile Updated", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Builder Profile Updated"

    activated = await client.post(f"/api/v1/pipelines/profiles/{profile_id}:activate", headers=tenant_headers)
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True

    headers = {**tenant_headers, "Idempotency-Key": "builder-profile-run-idem"}
    run_resp = await client.post(
        "/api/v1/pipelines/runs",
        headers=headers,
        json={"profile_id": profile_id, "inputs": {"template_version_id": "tv-2"}},
    )
    assert run_resp.status_code == 202

    runs_resp = await client.get("/api/v1/pipelines/runs", headers=tenant_headers, params={"q": "builder-profile-v2"})
    assert runs_resp.status_code == 200
    assert any(r["run_id"] == run_resp.json()["run_id"] for r in runs_resp.json())
