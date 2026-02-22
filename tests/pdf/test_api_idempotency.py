from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_convert_pdf_requires_idempotency(async_client, make_auth_headers) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers()}
    response = await async_client.post(
        "/api/v1/files/123/convert:pdf",
        json={"mode": "docx_to_pdf", "options": {"timeout_s": 45, "embed_fonts": True}},
        headers=headers,
    )
    assert response.status_code == 400
