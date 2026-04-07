from __future__ import annotations

import hashlib
import logging
import re
import zipfile
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from io import BytesIO
from typing import BinaryIO

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import select

from app.api.routes.files import max_upload_bytes
from app.core.config import get_settings
from app.domains.files import s3
from app.models.file import File as StoredFile
from app.models.file import FileKind, FileScanStatus
from app.models.models import AuditLog, RoleEnum
from app.services.clamav import (
    ClamAVScanRequest,
        ClamAVScanOutcome,
        ClamAVVerdict,
        MemoryQuarantinePublisher,
        get_quarantine_publisher,
        process_scan_request,
        reset_clamav_client,
        reset_quarantine_publisher,
)


def _minimal_docx_bytes() -> bytes:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w") as archive:
                archive.writestr(
                        "[Content_Types].xml",
                        """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
    <Default Extension="xml" ContentType="application/xml"/>
    <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
                )
                archive.writestr(
                        "_rels/.rels",
                        """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
    <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
                )
                archive.writestr(
                        "word/document.xml",
                        """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p><w:r><w:t>Template</w:t></w:r></w:p>
    </w:body>
</w:document>""",
                )
        return buffer.getvalue()


@pytest.fixture(autouse=True)
def _configure_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_BACKEND", "minio")
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_SECURE", "false")
    monkeypatch.setenv("PRESIGN_DOWNLOAD_TTL_SECONDS", "600")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", str(32_000_000))
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "60")
    monkeypatch.setenv(
        "FILE_ALLOWED_MIME",
        "text/plain,image/png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    monkeypatch.setenv("FILE_ALLOWED_EXTENSIONS", "txt,png,docx")
    monkeypatch.setenv("CLAMAV_QUEUE_URL", "memory://")
    monkeypatch.setenv("CLAMAV_QUARANTINE_QUEUE", "clamav.scan")
    monkeypatch.setenv("CLAMAV_SCAN_QUEUE", "clamav.scan")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    reset_quarantine_publisher()
    reset_clamav_client()
    s3.reset_client_cache()
    monkeypatch.setattr(
        "app.domains.files.s3.generate_presigned_get_url",
        lambda key, *, expires_in=3600, bucket=None, response_headers=None: (
            f"https://example.com/download/{key}?expires_in={expires_in}"
        ),
    )
    yield
    reset_quarantine_publisher()
    reset_clamav_client()
    s3.reset_client_cache()


@pytest.fixture()
def aws() -> None:
    moto = pytest.importorskip("moto", reason="moto is required for S3 integration tests")
    with moto.mock_aws():
        s3.ensure_bucket()
        yield


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_happy_path(async_client, make_auth_headers, sessionmaker) -> None:
    payload = b"Hello, storage!"
    filename = "greeting.txt"
    mime = "text/plain"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": (filename, payload, mime)},
        headers=headers,
    )
    assert response.status_code == 201

    body = response.json()
    assert body["mime"] == mime
    assert body["size"] == len(payload)
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["kind"] == FileKind.DOCUMENT.value
    assert body["original_name"] == filename
    assert body["storage_key"].startswith("tenants/")
    assert body["download_url"] is None
    assert body["quarantined"] is True
    assert body["scan_status"] == FileScanStatus.PENDING.value
    assert body["metadata"] == {}
    assert response.headers["ETag"] == body["sha256"]

    metadata = s3.head_object(key=body["storage_key"])
    assert metadata is not None
    assert metadata["size"] == len(payload)
    assert metadata["content_type"] == mime

    now = datetime.now(timezone.utc)
    expected_prefix = f'tenants/{headers["x-tenant"]}/kind/document/{now.year:04d}/{now.month:02d}/'
    assert body["storage_key"].startswith(expected_prefix)
    suffix = body["storage_key"][len(expected_prefix) :]
    assert re.fullmatch(r"[0-9a-f]{64}-[0-9a-f]{32}\.txt", suffix)

    async with sessionmaker() as session:
        record = await session.scalar(
            select(StoredFile).where(StoredFile.storage_key == body["storage_key"])
        )
        assert record is not None
        assert record.id == body["id"]
        assert record.sha256 == body["sha256"]
        assert record.size == len(payload)
        assert record.mime == mime
        assert record.is_quarantined is True
        assert record.scan_status == FileScanStatus.PENDING
        assert record.clamav_signature is None
        assert record.clamav_scanned_at is None

    publisher = get_quarantine_publisher()
    assert isinstance(publisher, MemoryQuarantinePublisher)
    messages = publisher.drain()
    assert len(messages) == 1
    message = messages[0]
    assert message.bucket == get_settings().s3_bucket
    assert message.key == body["storage_key"]
    assert message.size == len(payload)
    assert message.mime == mime
    assert message.sha256 == body["sha256"]
    assert message.tenant_slug == "test"

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(
                status=ClamAVVerdict.CLEAN,
                signature=None,
                raw="OK",
            )

    await process_scan_request(
        message,
        scanner=_CleanScanner(),
        session_factory=sessionmaker,
    )

    async with sessionmaker() as session:
        refreshed = await session.scalar(select(StoredFile).where(StoredFile.id == body["id"]))
        assert refreshed is not None
        assert refreshed.is_quarantined is False
        assert refreshed.scan_status == FileScanStatus.CLEAN
        assert refreshed.clamav_signature is None
        assert refreshed.clamav_scanned_at is not None

    detail_response = await async_client.get(
        f"/api/v1/files/{body['id']}",
        headers=headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["quarantined"] is False
    assert detail["scan_status"] == FileScanStatus.CLEAN.value
    assert detail["download_url"] == (
        f"https://example.com/download/{body['storage_key']}?expires_in=600"
    )


@pytest.mark.anyio
async def test_upload_uses_streaming_payload_for_storage(
    async_client,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_put_object(*, data, mime: str, key: str, size: int | None = None):
        captured["is_bytes"] = isinstance(data, (bytes, bytearray))
        captured["has_read"] = hasattr(data, "read")
        captured["mime"] = mime
        captured["key"] = key
        captured["size"] = size
        return ""

    monkeypatch.setattr("app.api.routes.files.s3.put_object", _fake_put_object)

    payload = b"stream-me"
    headers = {**dict(async_client.headers), **await make_auth_headers()}
    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("stream.txt", payload, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    assert captured["is_bytes"] is False
    assert captured["has_read"] is True
    assert captured["size"] == len(payload)


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_rejects_oversized(async_client, make_auth_headers) -> None:
    limit = max_upload_bytes()
    payload = b"a" * (limit + 1)
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("too-big.pdf", payload, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 413
    body = response.json()
    assert body["code"] in ("http_413", "FILE_TOO_LARGE", "PAYLOAD_TOO_LARGE")
    assert "exceed" in body["message"].lower() or "large" in body["message"].lower()
    details = body.get("details") or {}
    if "limit" in details:
        assert details["limit"] == limit
    if "size" in details:
        assert details["size"] == len(payload)
    assert body["trace_id"]


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_same_payload_produces_unique_keys(
    async_client, make_auth_headers
) -> None:
    payload = b"Hello, storage!"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    first = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("greeting.txt", payload, "text/plain")},
        headers=headers,
    )
    second = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("greeting.txt", payload, "text/plain")},
        headers=headers,
    )

    assert first.status_code == second.status_code == 201
    first_body = first.json()
    second_body = second.json()

    assert first_body["sha256"] == second_body["sha256"]
    assert first_body["storage_key"] != second_body["storage_key"]
    assert first_body["download_url"] is None
    assert second_body["download_url"] is None


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_rejects_unsupported_mime(async_client, make_auth_headers) -> None:
    payload = b"binary"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("payload.bin", payload, "application/octet-stream")},
        headers=headers,
    )

    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "http_415"
    assert body["message"] == "Unsupported MIME type"
    assert body["trace_id"]


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_rejects_mismatched_extension(async_client, make_auth_headers) -> None:
    payload = b"plain text pretending to be pdf"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("report.pdf", payload, "text/plain")},
        headers=headers,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "http_400"
    assert body["message"] == "File extension does not match detected content"
    assert body["trace_id"]


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_file_rejects_disallowed_extension(async_client, make_auth_headers) -> None:
    payload = b"%PDF-1.7 fake"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("report.pdf", payload, "application/pdf")},
        headers=headers,
    )

    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "http_415"
    assert body["message"] == "Unsupported file extension"
    assert body["trace_id"]


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_rejects_cross_tenant_scope(async_client, make_auth_headers) -> None:
    payload = b"Hello scope"
    headers = {**await make_auth_headers(), "x-tenant": "acme"}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("note.txt", payload, "text/plain")},
        headers=headers,
    )

    assert response.status_code in {400, 403}


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_clamav_detects_infected_and_blocks_download(
    async_client,
    make_auth_headers,
    sessionmaker,
    caplog,
) -> None:
    payload = b"test-payload"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("virus.txt", payload, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()

    publisher = get_quarantine_publisher()
    message = publisher.drain()[0]

    class _InfectedScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(
                status=ClamAVVerdict.INFECTED,
                signature="Eicar-Test-Signature",
                raw="FOUND",
            )

    with caplog.at_level(logging.WARNING):
        await process_scan_request(
            message,
            scanner=_InfectedScanner(),
            session_factory=sessionmaker,
        )
        assert any("files.clamav.detected" in record.message for record in caplog.records)

    detail = await async_client.get(f"/api/v1/files/{body['id']}", headers=headers)
    assert detail.status_code == 200
    data = detail.json()
    assert data["quarantined"] is True
    assert data["scan_status"] == FileScanStatus.INFECTED.value
    assert data["download_url"] is None

    async with sessionmaker() as session:
        record = await session.scalar(select(StoredFile).where(StoredFile.id == body["id"]))
        assert record is not None
        assert record.is_quarantined is True
        assert record.scan_status == FileScanStatus.INFECTED
        assert record.clamav_signature == "Eicar-Test-Signature"


@pytest.mark.anyio
async def test_process_scan_request_uses_canonical_tenant_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = ClamAVScanRequest(
        bucket="bucket-a",
        key="uploads/test.txt",
        size=4,
        mime="text/plain",
        sha256="a" * 64,
        tenant_id="00000000-0000-0000-0000-000000000123",
        tenant_slug="test",
    )
    captured: dict[str, str] = {}

    class _Result:
        def scalar_one_or_none(self):
            return None

    class _Session:
        async def execute(self, *_args, **_kwargs):
            return _Result()

        async def flush(self):
            return None

    @asynccontextmanager
    async def fake_get_tenant_session(*, tenant: str | None = None, tenant_id: str | None = None, schema_name: str | None = None):
        del schema_name
        captured["tenant"] = tenant or ""
        captured["tenant_id"] = tenant_id or ""
        yield _Session()

    @contextmanager
    def fake_stream_object(*, key: str):
        assert key == message.key
        yield BytesIO(b"scan")

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            assert stream.read() == b"scan"
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, raw="OK")

    monkeypatch.setattr("app.services.clamav.get_tenant_session", fake_get_tenant_session)
    monkeypatch.setattr("app.services.clamav.s3.stream_object", fake_stream_object)

    outcome = await process_scan_request(message, scanner=_CleanScanner())

    assert outcome.status == ClamAVVerdict.CLEAN
    assert captured == {"tenant": "test", "tenant_id": "00000000-0000-0000-0000-000000000123"}


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_upload_template_adds_metadata(async_client, make_auth_headers, sessionmaker) -> None:
    payload = _minimal_docx_bytes()
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload-template",
        files={"file": ("template.docx", payload, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"template_type": "contract", "scenario": "onboarding", "pack_id": "pack-1", "company_id": "comp-1"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == FileKind.TEMPLATE.value
    assert body["metadata"]["template_type"] == "contract"
    assert body["metadata"]["scenario"] == "onboarding"
    assert body["pack_id"] == "pack-1"
    assert body["company_id"] == "comp-1"
    assert "scenario/onboarding" in body["storage_key"]
    assert "/kind/template/" in body["storage_key"]


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_download_endpoint_returns_presigned_url(
    async_client, make_auth_headers, sessionmaker
) -> None:
    payload = b"downloadable"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    upload = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("note.txt", payload, "text/plain")},
        headers=headers,
    )
    body = upload.json()
    publisher = get_quarantine_publisher()
    message = publisher.drain()[0]

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw="OK")

    await process_scan_request(message, scanner=_CleanScanner(), session_factory=sessionmaker)

    download = await async_client.get(f"/api/v1/files/{body['id']}/download", headers=headers)
    assert download.status_code == 200
    data = download.json()
    assert data["id"] == body["id"]
    assert data["url"] == f"https://example.com/download/{body['storage_key']}?expires_in=600"
    expires_at = datetime.fromisoformat(data["expires_at"])
    assert expires_at.tzinfo is not None
    assert expires_at > datetime.now(timezone.utc)

    async with sessionmaker() as session:
        entry = await session.scalar(
            select(AuditLog).where(
                AuditLog.action == "FileDownloadPresigned",
                AuditLog.object_type == "file",
                AuditLog.object_id == body["id"],
            )
        )
        assert entry is not None


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_download_blocks_file_while_scan_pending(
    async_client, make_auth_headers
) -> None:
    payload = b"pending-check"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    upload = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("pending.txt", payload, "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["scan_status"] == FileScanStatus.PENDING.value
    assert body["quarantined"] is True

    download = await async_client.get(f"/api/v1/files/{body['id']}/download", headers=headers)
    assert download.status_code == 409
    data = download.json()
    assert data["code"] == "FILE_NOT_READY"
    assert data["message"] == "File is not available for download until antivirus scan is clean"


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_download_denies_cross_tenant(async_client, make_auth_headers, sessionmaker) -> None:
    payload = b"tenant-check"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    upload = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("note.txt", payload, "text/plain")},
        headers=headers,
    )
    body = upload.json()
    publisher = get_quarantine_publisher()
    message = publisher.drain()[0]

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw="OK")

    await process_scan_request(message, scanner=_CleanScanner(), session_factory=sessionmaker)

    bad_headers = {**headers, "x-tenant": "acme"}
    download = await async_client.get(f"/api/v1/files/{body['id']}/download", headers=bad_headers)
    assert download.status_code == 403


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_download_denies_company_mismatch(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="Alpha Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="Beta Co", session=session)
        await session.commit()

    payload = b"company-check"
    admin_headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}
    upload = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("note.txt", payload, "text/plain")},
        data={"company_id": company_a.id},
        headers=admin_headers,
    )
    body = upload.json()
    publisher = get_quarantine_publisher()
    message = publisher.drain()[0]

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw="OK")

    await process_scan_request(message, scanner=_CleanScanner(), session_factory=sessionmaker)

    client_headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.CLIENT_USER, company_id=company_b.id)}
    download = await async_client.get(f"/api/v1/files/{body['id']}/download", headers=client_headers)
    assert download.status_code == 403


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_get_file_returns_404_when_object_missing(
    async_client,
    make_auth_headers,
    sessionmaker,
) -> None:
    payload = b"temporary"
    headers = {**dict(async_client.headers), **await make_auth_headers()}

    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("temp.txt", payload, "text/plain")},
        headers=headers,
    )
    body = response.json()
    publisher = get_quarantine_publisher()
    message = publisher.drain()[0]

    class _CleanScanner:
        def scan_stream(self, stream: BinaryIO) -> ClamAVScanOutcome:
            stream.read()
            return ClamAVScanOutcome(status=ClamAVVerdict.CLEAN, signature=None, raw="OK")

    await process_scan_request(
        message,
        scanner=_CleanScanner(),
        session_factory=sessionmaker,
    )

    client = s3.get_client()
    client.delete_object(Bucket=get_settings().s3_bucket, Key=body["storage_key"])

    detail = await async_client.get(f"/api/v1/files/{body['id']}", headers=headers)
    assert detail.status_code == 404
    data = detail.json()
    assert data["code"] == "http_404"
    assert data["details"]["storage_code"] == "storage_not_found"


@pytest.mark.anyio
async def test_upload_returns_503_when_bucket_unavailable(
    async_client, make_auth_headers, monkeypatch
) -> None:
    class _BrokenClient:
        def put_object(self, **kwargs):
            raise ClientError(
                {
                    "Error": {
                        "Code": "NoSuchBucket",
                        "Message": "Bucket does not exist",
                    },
                    "ResponseMetadata": {"RequestId": "req-123"},
                },
                "PutObject",
            )

    monkeypatch.setattr("app.domains.files.s3.get_client", lambda: _BrokenClient())

    headers = {**dict(async_client.headers), **await make_auth_headers()}
    response = await async_client.post(
        "/api/v1/files/upload",
        files={"file": ("broken.txt", b"content", "text/plain")},
        headers=headers,
    )

    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "http_503"
    assert body["details"]["storage_code"] == "storage_unavailable"
