from __future__ import annotations

import io

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from starlette import status
from starlette.datastructures import UploadFile

from app.api.helpers.upload import reject_oversize_upload
from app.core.config import get_settings


def _upload(size: int) -> UploadFile:
    return UploadFile(file=io.BytesIO(b"x" * size), size=size, filename="payload.bin")


def test_reject_oversize_upload_raises_above_limit() -> None:
    with pytest.raises(HTTPException) as excinfo:
        reject_oversize_upload(
            _upload(11), code="X_TOO_LARGE", error_type="x", max_bytes=10
        )

    assert excinfo.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    assert excinfo.value.detail["code"] == "X_TOO_LARGE"
    assert excinfo.value.detail["type"] == "x"


def test_reject_oversize_upload_allows_at_limit() -> None:
    # Exactly at the limit must pass — guard is strictly greater-than.
    reject_oversize_upload(_upload(10), code="X_TOO_LARGE", error_type="x", max_bytes=10)


def test_reject_oversize_upload_defaults_to_settings_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    try:
        with pytest.raises(HTTPException) as excinfo:
            reject_oversize_upload(_upload(11), code="X_TOO_LARGE", error_type="x")
        assert excinfo.value.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    finally:
        get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_document_batch_rejects_oversized_file(
    async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    oversized_csv = b"person_id,name\n,Alpha\n,Beta\n"  # well over 10 bytes

    response = await async_client.post(
        "/api/v1/documents/batch",
        files={"file": ("batch.csv", oversized_csv, "text/csv")},
        data={
            "template_code": "Greeting",
            "template_version": 1,
            "company_id": "demo-company",
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    body = response.json()
    assert body["code"] == "DOCUMENT_BATCH_FILE_TOO_LARGE"
    assert body["trace_id"]

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_replace_map_rejects_oversized_csv(
    async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    # /replace-maps is the *mounted* multipart endpoint (app.modules.replace.api);
    # the legacy app.api.routes.replace router is dead code and not wired into v1.
    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    oversized_csv = b"from,to\nAlpha,Beta\nGamma,Delta\n"  # over 10 bytes

    response = await async_client.post(
        "/api/v1/replace-maps",
        files={"replace_csv": ("map.csv", oversized_csv, "text/csv")},
        headers=headers,
    )

    assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    body = response.json()
    assert body["code"] == "REPLACE_MAP_UPLOAD_TOO_LARGE"
    assert body["trace_id"]

    get_settings.cache_clear()  # type: ignore[attr-defined]
