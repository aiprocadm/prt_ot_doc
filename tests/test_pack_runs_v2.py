from __future__ import annotations

import base64
import uuid
from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from app.models.file import File, FileKind, FileScanStatus


@pytest.mark.anyio
async def test_pack_runs_requires_tenant_and_idem(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pack-runs", json={"package_preset_id": "x"}, headers=headers
    )
    assert response.status_code == 400
    assert "Idempotency-Key" in response.text


@pytest.mark.anyio
async def test_pack_run_idempotent_returns_same_run_id(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    profile_payload = {
        "code": f"pp-{uuid.uuid4().hex[:8]}",
        "name": "Profile",
        "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
        "status": "active",
    }
    p_resp = await async_client.post(
        "/api/v1/package-profiles", json=profile_payload, headers=headers
    )
    assert p_resp.status_code == 201, p_resp.text
    profile_id = p_resp.json()["id"]

    preset_payload = {
        "code": f"preset-{uuid.uuid4().hex[:8]}",
        "name": "Preset",
        "package_profile_id": profile_id,
        "naming_rule": "<doc>_<date>",
        "source_type": "json",
        "mapping_json": {
            "doc": {"type": "literal", "value": "test"},
            "date": {"type": "literal", "value": "20260329"},
        },
        "status": "active",
    }
    preset_resp = await async_client.post(
        "/api/v1/package-presets", json=preset_payload, headers=headers
    )
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


@pytest.mark.anyio
async def test_pack_run_unique_filenames_when_same_mapping(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    profile_payload = {
        "code": f"pp-{uuid.uuid4().hex[:8]}",
        "name": "Profile",
        "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
        "status": "active",
    }
    p_resp = await async_client.post(
        "/api/v1/package-profiles", json=profile_payload, headers=headers
    )
    assert p_resp.status_code == 201, p_resp.text
    profile_id = p_resp.json()["id"]

    preset_payload = {
        "code": f"preset-{uuid.uuid4().hex[:8]}",
        "name": "Preset",
        "package_profile_id": profile_id,
        "naming_rule": "<doc>",
        "source_type": "json",
        "mapping_json": {"doc": {"type": "literal", "value": "same"}},
        "status": "active",
    }
    preset_resp = await async_client.post(
        "/api/v1/package-presets", json=preset_payload, headers=headers
    )
    assert preset_resp.status_code == 201, preset_resp.text
    preset_id = preset_resp.json()["id"]

    run_payload = {
        "package_preset_id": preset_id,
        "rows": [{"fio": "A"}, {"fio": "B"}],
        "selected_rows": [1, 2],
    }
    run_resp = await async_client.post(
        "/api/v1/pack-runs",
        json=run_payload,
        headers={**headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["pack_run_id"]

    items_resp = await async_client.get(f"/api/v1/pack-runs/{run_id}/items", headers=headers)
    assert items_resp.status_code == 200, items_resp.text
    filenames = [item["file_name"] for item in items_resp.json()]
    assert filenames == ["same.docx", "same_2.docx"]


@pytest.mark.anyio
async def test_preview_mapping_supports_xlsx_source(
    async_client: AsyncClient, sessionmaker, data_factory, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}

    profile_payload = {
        "code": f"pp-{uuid.uuid4().hex[:8]}",
        "name": "Profile",
        "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
        "status": "active",
    }
    p_resp = await async_client.post(
        "/api/v1/package-profiles", json=profile_payload, headers=headers
    )
    assert p_resp.status_code == 201, p_resp.text
    profile_id = p_resp.json()["id"]

    preset_payload = {
        "code": f"preset-{uuid.uuid4().hex[:8]}",
        "name": "Preset",
        "package_profile_id": profile_id,
        "naming_rule": "<doc>",
        "source_type": "xlsx",
        "mapping_json": {"doc": "фио", "unit": {"type": "column", "value": "подразделение"}},
        "status": "active",
    }
    preset_resp = await async_client.post(
        "/api/v1/package-presets", json=preset_payload, headers=headers
    )
    assert preset_resp.status_code == 201, preset_resp.text
    preset_id = preset_resp.json()["id"]

    wb = Workbook()
    ws = wb.active
    ws.append(["ФИО", "Подразделение"])
    ws.append(["Иванов И.И.", "Цех 1"])
    ws.append(["Петров П.П.", "Цех 2"])
    buf = BytesIO()
    wb.save(buf)

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        source_file = File(
            tenant_id=tenant.id,
            storage_key=f"inline/source-{uuid.uuid4().hex}.xlsx",
            bucket="inline",
            sha256="f" * 64,
            size=len(buf.getvalue()),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            kind=FileKind.DOCUMENT,
            scan_status=FileScanStatus.CLEAN,
            is_quarantined=False,
            meta_json={
                "source_type": "xlsx",
                "inline_content_b64": base64.b64encode(buf.getvalue()).decode("ascii"),
            },
        )
        session.add(source_file)
        await session.commit()
        await session.refresh(source_file)
        source_file_id = source_file.id

    preview_resp = await async_client.post(
        f"/api/v1/package-presets/{preset_id}:preview-mapping",
        json={"source_file_id": source_file_id, "row_limit": 2},
        headers=headers,
    )
    assert preview_resp.status_code == 200, preview_resp.text
    body = preview_resp.json()
    assert body["source_type"] == "xlsx"
    assert body["preview"][0]["doc"] == "Иванов И.И."
    assert body["preview"][0]["unit"] == "Цех 1"


@pytest.mark.anyio
async def test_pack_run_naming_rule_supports_yyyymmdd_token(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**await make_auth_headers(), **dict(async_client.headers)}
    profile_payload = {
        "code": f"pp-{uuid.uuid4().hex[:8]}",
        "name": "Profile",
        "pipeline_steps_json": [{"step": "render_docx", "enabled": True}],
        "status": "active",
    }
    p_resp = await async_client.post(
        "/api/v1/package-profiles", json=profile_payload, headers=headers
    )
    assert p_resp.status_code == 201, p_resp.text
    profile_id = p_resp.json()["id"]

    preset_payload = {
        "code": f"preset-{uuid.uuid4().hex[:8]}",
        "name": "Preset",
        "package_profile_id": profile_id,
        "naming_rule": "<doc>_<YYYYMMDD>",
        "source_type": "json",
        "mapping_json": {"doc": {"type": "literal", "value": "акт"}},
        "status": "active",
    }
    preset_resp = await async_client.post(
        "/api/v1/package-presets", json=preset_payload, headers=headers
    )
    assert preset_resp.status_code == 201, preset_resp.text
    preset_id = preset_resp.json()["id"]

    run_resp = await async_client.post(
        "/api/v1/pack-runs",
        json={"package_preset_id": preset_id, "rows": [{"fio": "A"}], "selected_rows": [1]},
        headers={**headers, "Idempotency-Key": f"idem-{uuid.uuid4().hex}"},
    )
    assert run_resp.status_code == 202, run_resp.text
    run_id = run_resp.json()["pack_run_id"]

    items_resp = await async_client.get(f"/api/v1/pack-runs/{run_id}/items", headers=headers)
    assert items_resp.status_code == 200, items_resp.text
    filename = items_resp.json()[0]["file_name"]
    assert filename.startswith("акт_")
    assert filename.endswith(".docx")
    assert len(filename.split("_")[1].split(".")[0]) == 8
