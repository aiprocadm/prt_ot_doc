from __future__ import annotations

from io import BytesIO

import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_replace_dry_run_apply_rollback(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    transport = ASGITransport(app=app_fixture)

    doc = Document()
    doc.add_paragraph("Hello {{company_name}}")
    table = doc.add_table(rows=1, cols=1)
    table.rows[0].cells[0].text = "{{company_name}} in table"
    doc.sections[0].header.add_paragraph("{{company_name}}")
    doc.sections[0].footer.add_paragraph("{{company_name}}")
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    mapping = b"from;to\n{{company_name}};OOO Demo\n"

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        dry = await client.post(
            "/api/v1/replace:dry-run",
            headers=headers,
            files={
                "docx_file": ("demo.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "replace_map": ("replace_map.csv", mapping, "text/csv"),
            },
        )
        assert dry.status_code == 202
        dry_payload = dry.json()
        assert dry_payload["summary"]["matches"] >= 3
        report_id = dry_payload["report_id"]

        report = await client.get(f"/api/v1/replace/reports/{report_id}", headers=headers)
        assert report.status_code == 200
        assert report.json()["total"] >= 3

        apply = await client.post(
            "/api/v1/replace:apply",
            headers=headers,
            files={
                "docx_file": ("demo.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "replace_map": ("replace_map.csv", mapping, "text/csv"),
            },
        )
        assert apply.status_code == 202
        apply_payload = apply.json()
        assert apply_payload["backup_file_id"]

        rollback = await client.post(
            "/api/v1/replace:rollback",
            headers=headers,
            params={"apply_job_id": apply_payload["job_id"]},
        )
        assert rollback.status_code == 202
        assert rollback.json()["restored_file_id"]


@pytest.mark.anyio
async def test_replace_requires_tenant_header(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture)

    doc = Document()
    doc.add_paragraph("Hello")
    buffer = BytesIO()
    doc.save(buffer)

    mapping = b"from,to\nHello,Hi\n"

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        dry = await client.post(
            "/api/v1/replace/dry-run",
            files={
                "docx_file": ("demo.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "replace_map": ("replace_map.csv", mapping, "text/csv"),
            },
        )
    assert dry.status_code == 400
