from __future__ import annotations

import pytest
from httpx import AsyncClient
from starlette import status

from app.core.config import get_settings


def _build_csv(rows: list[dict[str, str]]) -> bytes:
    headers = rows[0].keys()
    output = ",".join(headers) + "\n"
    output += "\n".join(",".join(str(row[h]) for h in headers) for row in rows)
    return output.encode("utf-8")


@pytest.mark.anyio
async def test_document_batch_rejects_excess_rows(
    async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_BATCH_MAX_ROWS", "1")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    csv_payload = _build_csv(
        [
            {"person_id": "", "name": "Alpha"},
            {"person_id": "", "name": "Beta"},
        ]
    )

    response = await async_client.post(
        "/api/v1/documents/batch",
        files={"file": ("batch.csv", csv_payload, "text/csv")},
        data={
            "template_code": "Greeting",
            "template_version": 1,
            "company_id": "demo-company",
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    body = response.json()
    assert body["code"] == "DOCUMENT_BATCH_TOO_MANY_ROWS"
    assert body["message"] == "Batch cannot exceed 1 documents"
    assert body["trace_id"]

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_document_payload_rejects_large_payload(
    async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCUMENT_PAYLOAD_MAX_BYTES", "50")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    oversized = "x" * 200
    response = await async_client.post(
        "/api/v1/documents/generate",
        json={
            "template_code": "Greeting",
            "template_version": 1,
            "company_id": "demo-company",
            "data": {"note": oversized},
        },
        headers={**headers, "Idempotency-Key": "limit-check"},
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    body = response.json()
    assert body["code"] == "DOCUMENT_PAYLOAD_TOO_LARGE"
    assert body["message"] == "data payload cannot exceed 50 bytes"
    assert body["trace_id"]

    get_settings.cache_clear()  # type: ignore[attr-defined]
