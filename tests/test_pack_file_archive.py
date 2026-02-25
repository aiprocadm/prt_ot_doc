import zipfile
from io import BytesIO
from typing import BinaryIO

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.files import s3
from app.models.file import File as StoredFile, FileScanStatus
from app.services.clamav import (
    ClamAVScanOutcome,
    ClamAVVerdict,
    get_quarantine_publisher,
    process_scan_request,
    reset_clamav_client,
    reset_quarantine_publisher,
)


@pytest.fixture(autouse=True)
def _configure_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_BACKEND", "minio")
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_SECURE", "false")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", str(32_000_000))
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain,image/png")
    monkeypatch.setenv("FILE_ALLOWED_EXTENSIONS", "txt")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    reset_quarantine_publisher()
    reset_clamav_client()
    s3.reset_client_cache()
    yield
    reset_quarantine_publisher()
    reset_clamav_client()
    s3.reset_client_cache()


@pytest.fixture()
def aws() -> None:
    mock_aws = pytest.importorskip("moto").mock_aws

    with mock_aws():
        s3.ensure_bucket()
        yield


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_pack_archive_collects_files(async_client, make_auth_headers, sessionmaker) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw="OK")

    for idx in range(2):
        payload = f"document-{idx}".encode()
        upload = await async_client.post(
            "/api/v1/files/upload",
            files={"file": (f"doc-{idx}.txt", payload, "text/plain")},
            data={"pack_id": "pack-zip"},
            headers=headers,
        )
        assert upload.status_code == 201
        message = get_quarantine_publisher().drain()[0]
        await process_scan_request(message, scanner=_CleanScanner(), session_factory=sessionmaker)

    archive = await async_client.get(
        "/api/v1/packs/pack-zip/download-archive",
        headers=headers,
    )
    assert archive.status_code == 200
    with zipfile.ZipFile(BytesIO(archive.content)) as bundle:
        names = sorted(bundle.namelist())
        assert names == ["doc-0.txt", "doc-1.txt"]
        assert bundle.read("doc-0.txt") == b"document-0"
        assert bundle.read("doc-1.txt") == b"document-1"

    async with sessionmaker() as session:
        stored = list(
            (await session.scalars(
                select(StoredFile).where(StoredFile.pack_id == "pack-zip")
            )).all()
        )
        assert len(stored) == 2
        assert all(record.scan_status == FileScanStatus.CLEAN for record in stored)
