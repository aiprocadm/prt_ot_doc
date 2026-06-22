import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.services.file_storage import FileStorageService


@pytest.mark.anyio
async def test_pack_download_stream(
    async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("S3_BACKEND", "local")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    storage = FileStorageService.default()
    key = "tenants/test/packages/demo/archive.zip"
    payload = b"PK\x03\x04demo"
    storage.put(key, payload, content_type="application/zip")

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    response = await async_client.get(
        "/api/v1/packs/download",
        params={"storage_key": key},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].endswith('archive.zip"')
    assert response.headers["content-length"] == str(len(payload))
    assert response.content == payload

    monkeypatch.delenv("S3_BACKEND", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_pack_download_presigned_redirect(
    async_client: AsyncClient,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FileStorageService.default()
    key = "tenants/test/packages/demo/archive.zip"
    storage.put(key, b"payload", content_type="application/zip")

    monkeypatch.setenv("S3_BACKEND", "minio")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    captured: dict[str, object] = {}

    def fake_presign(
        key: str, *, expires_in: int = 3600, bucket: str | None = None, response_headers=None
    ) -> str:
        captured["key"] = key
        captured["expires_in"] = expires_in
        return "https://example.com/presigned"

    monkeypatch.setattr(
        "app.domains.files.s3.generate_presigned_get_url",
        fake_presign,
    )

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    response = await async_client.get(
        "/api/v1/packs/download",
        params={"storage_key": key},
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com/presigned"
    assert captured["key"] == key
    assert captured["expires_in"] == 3600

    monkeypatch.delenv("S3_BACKEND", raising=False)
    get_settings.cache_clear()  # type: ignore[attr-defined]
