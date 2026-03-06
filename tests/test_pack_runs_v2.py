from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.anyio
async def test_pack_runs_requires_tenant_and_idem(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers()
    response = await async_client.post("/api/v1/pack-runs", json={"package_preset_id": "x"}, headers=headers)
    assert response.status_code == 400
    assert "Idempotency-Key" in response.text


@pytest.mark.anyio
async def test_pack_run_idempotent_returns_same_run_id(async_client: AsyncClient, sessionmaker, make_auth_headers) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    profile_payload = {
            "code": f"pp-{uuid.uuid4().hex[:8]}",
            "name": "Profile",
            "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
            "status": "active",
        }
    p_resp = await async_client.post("/api/v1/package-profiles", json=profile_payload, headers=headers)
    assert p_resp.status_code == 201, p_resp.text
    profile_id = p_resp.json()["id"]

    preset_payload = {
        "code": f"preset-{uuid.uuid4().hex[:8]}",
        "name": "Preset",
        "package_profile_id": profile_id,
        "naming_rule": "<doc>_<date>",
        "source_type": "json",
        "mapping_json": {"doc": {"type": "literal", "value": "test"}, "date": {"type": "literal", "value": "20260329"}},
        "status": "active",
    }
    preset_resp = await async_client.post("/api/v1/package-presets", json=preset_payload, headers=headers)
    assert preset_resp.status_code == 201, preset_resp.text
    preset_id = preset_resp.json()["id"]

    run_payload = {
        "package_preset_id": preset_id,
        "rows": [{"fio": "Иванов"}, {"fio": "Петров"}],
        "selected_rows": [1],
    }
    idem_key = f"idem-{uuid.uuid4().hex}"
    first = await async_client.post(
        "/api/v1/pack-runs",
        json=run_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert first.status_code == 202, first.text
    second = await async_client.post(
        "/api/v1/pack-runs",
        json=run_payload,
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert second.status_code == 202, second.text
    assert first.json()["pack_run_id"] == second.json()["pack_run_id"]
