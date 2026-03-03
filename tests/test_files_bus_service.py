from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.files.models import FileDownloadLog, FileLink, FileRecord, FileStatus
from app.modules.files.service import FileService, compute_sha256_stream


class DummySession:
    def __init__(self, record: FileRecord | None = None) -> None:
        self.record = record
        self.added: list[object] = []

    async def get(self, model, id_):
        if self.record is not None and id_ == self.record.id:
            return self.record
        return None

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def execute(self, stmt):
        return None


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [([b"hello", b" ", b"world"], "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9")],
)
def test_compute_sha256_stream(chunks: list[bytes], expected: str) -> None:
    assert compute_sha256_stream(chunks) == expected


@pytest.mark.asyncio
async def test_download_blocked_if_not_clean() -> None:
    rec = FileRecord(id="f1", tenant_id="t1", bucket="main", object_key="a", content_type="text/plain", size_bytes=1, sha256="a" * 64, status=FileStatus.scanning.value, av_result_json={}, metadata_json={})
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    with pytest.raises(HTTPException) as exc:
        await svc.get_signed_download_url(file_id="f1", purpose="api")

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_link_and_unlink_file() -> None:
    rec = FileRecord(id="f2", tenant_id="t1", bucket="main", object_key="a", content_type="text/plain", size_bytes=1, sha256="b" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={})
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    link = await svc.link_file(file_id="f2", entity_type="job", entity_id="j1", role="artifact")

    assert isinstance(link, FileLink)
    assert link.file_id == "f2"
    assert any(isinstance(item, FileLink) for item in session.added)

    await svc.unlink_file(file_id="f2", entity_type="job", entity_id="j1", role="artifact")
    assert True


@pytest.mark.asyncio
async def test_download_creates_log(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FileRecord(id="f3", tenant_id="t1", bucket="main", object_key="k", content_type="text/plain", size_bytes=1, sha256="c" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={})
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setattr("app.modules.files.storage.presign_get", lambda *, key, expires_in: "http://signed")
    url = await svc.get_signed_download_url(file_id="f3", purpose="ui_preview", ip="127.0.0.1", user_agent="pytest")

    assert url == "http://signed"
    assert any(isinstance(item, FileDownloadLog) for item in session.added)


def test_build_artifact_name_supports_flags_and_sanitizes() -> None:
    from app.modules.files.service import build_artifact_name

    name = build_artifact_name(
        {
            "org": "АО Ромашка",
            "unit": "Unit 1",
            "project": "Proj",
            "client": "Client",
            "doc": "DOC",
            "topic": "Topic Name",
            "version": 3,
            "date": "2026-03-12",
            "flags": ["draft", "for sign"],
        },
        ext="pdf",
    )

    assert name == "ао-ромашка_unit-1_proj_client_doc_topic-name_v03_20260312_draft_for-sign.pdf"


@pytest.mark.asyncio
async def test_create_upload_session_validates_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    rec = FileRecord(id="f4", tenant_id="t1", bucket="main", object_key="a", content_type="text/plain", size_bytes=1, sha256="d" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={})
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(HTTPException) as exc:
        await svc.create_upload_session(filename="a.txt", content_type="text/plain", size_bytes=11)

    assert exc.value.status_code == 413

    with pytest.raises(HTTPException) as exc2:
        await svc.create_upload_session(filename="a.pdf", content_type="application/pdf", size_bytes=5)

    assert exc2.value.status_code == 415

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_create_upload_session_uses_tenant_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    session = DummySession(None)
    svc = FileService(session=session, tenant_id="tenant-xyz")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    monkeypatch.setattr("app.modules.files.service.s3.generate_presigned_put_url", lambda key, **kwargs: "http://put")
    rec, _url, _ttl = await svc.create_upload_session(filename="a.txt", content_type="text/plain", size_bytes=1)
    assert rec.object_key.startswith("tenants/tenant-xyz/")
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_av_scan_infected_moves_to_quarantine(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FileRecord(id="f5", tenant_id="t1", bucket="main", object_key="tenants/t1/uploads/a.txt", content_type="text/plain", size_bytes=1, sha256="e" * 64, status=FileStatus.scanning.value, av_result_json={}, metadata_json={})
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    class _Body:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return b"bad"

    class _Verdict:
        status = "infected"
        signature = "Eicar-Test-Signature"

    monkeypatch.setattr("app.modules.files.service.s3.stream_object", lambda *, key: _Body())
    monkeypatch.setattr("app.modules.files.service.s3.put_object", lambda *, data, mime, key: None)
    monkeypatch.setattr("app.modules.files.service.av.scan_file", lambda _path: _Verdict())

    await svc.av_scan_file(file_id="f5")

    assert rec.status == FileStatus.quarantined.value
    assert rec.object_key.startswith("quarantine/")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class DummySessionWithVersion(DummySession):
    async def execute(self, stmt):
        return _ScalarResult(2)


@pytest.mark.asyncio
async def test_create_new_version_upload_session_uses_tenant_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.modules.files.models import FileVersion

    rec = FileRecord(
        id="f6", tenant_id="t1", bucket="main", object_key="tenants/t1/uploads/a.txt",
        content_type="text/plain", size_bytes=1, sha256="f" * 64, status=FileStatus.ready.value, av_result_json={}, metadata_json={}
    )
    session = DummySessionWithVersion(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr("app.modules.files.service.s3.generate_presigned_put_url", lambda key, **kwargs: f"http://put/{key}")

    version, upload_url, _ = await svc.create_new_version_upload_session(
        file_id="f6", filename="next.txt", content_type="text/plain", size_bytes=10
    )

    assert isinstance(version, FileVersion)
    assert version.version_no == 3
    assert version.s3_key.startswith("tenants/t1/files/f6/f6/3/")
    assert upload_url.startswith("http://put/tenants/t1/files/f6/f6/3/")
    get_settings.cache_clear()  # type: ignore[attr-defined]
