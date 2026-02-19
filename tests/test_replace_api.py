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
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    mapping = b"from,to\n{{company_name}},OOO Demo\n"

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        dry = await client.post(
            "/api/v1/replace/dry-run",
            headers=headers,
            files={
                "docx_file": ("demo.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "replace_map": ("replace_map.csv", mapping, "text/csv"),
            },
        )
        assert dry.status_code == 200
        assert dry.json()["total_occurrences"] >= 1

        apply = await client.post(
            "/api/v1/replace/apply",
            headers=headers,
            files={
                "docx_file": ("demo.docx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "replace_map": ("replace_map.csv", mapping, "text/csv"),
            },
        )
        assert apply.status_code == 200
        operation_id = apply.json()["operation_id"]

        rollback = await client.post(
            f"/api/v1/replace/rollback?operation_id={operation_id}",
            headers=headers,
        )
        assert rollback.status_code == 200
        assert rollback.json()["restored"] is True
