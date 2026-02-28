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
