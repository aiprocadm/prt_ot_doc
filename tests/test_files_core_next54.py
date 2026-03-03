from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.files.models import FileRecord, FileStatus
from app.modules.files.service import FileService
from app.modules.files.storage import assert_tenant_key, build_tenant_key


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class DummySession:
    def __init__(self, record: FileRecord | None = None, dedupe: FileRecord | None = None) -> None:
        self.record = record
        self.dedupe = dedupe
        self.added: list[object] = []

    async def get(self, _model, _id):
        return self.record if self.record and self.record.id == _id else None

    async def execute(self, _stmt):
        return _Scalar(self.dedupe)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def test_build_tenant_key_date_prefix() -> None:
    key = build_tenant_key(tenant_id="tenant-1", file_id="f1", filename="doc.pdf")
    assert key.startswith("tenant-1/")
    assert key.endswith("/f1/doc.pdf")


def test_assert_tenant_key_accepts_new_prefix() -> None:
    assert_tenant_key(tenant_id="tenant-1", key="tenant-1/2026/03/03/f1/doc.pdf")


@pytest.mark.asyncio
async def test_signed_url_blocked_for_infected() -> None:
    rec = FileRecord(id="f1", tenant_id="t1", bucket="ptd", object_key="t1/2026/03/03/f1/a.txt", content_type="text/plain", size_bytes=1, sha256="a" * 64, status=FileStatus.infected.value, av_result_json={}, metadata_json={})
    svc = FileService(session=DummySession(rec), tenant_id="t1")
    with pytest.raises(HTTPException) as exc:
        await svc.get_signed_download_url(file_id="f1", purpose="download")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_create_upload_session_dedupe_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    existing = FileRecord(id="existing", tenant_id="t1", bucket="ptd", object_key="t1/2026/03/03/existing/a.txt", content_type="text/plain", size_bytes=1, sha256="b" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={})
    session = DummySession(None, dedupe=existing)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    record, upload_url, ttl = await svc.create_upload_session(
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        metadata_json={"sha256": "b" * 64},
    )
    assert record.id == "existing"
    assert upload_url == ""
    assert ttl == 0
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_create_upload_session_dedupe_merges_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    existing = FileRecord(id="existing", tenant_id="t1", bucket="ptd", object_key="t1/2026/03/03/existing/a.txt", content_type="text/plain", size_bytes=1, sha256="b" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={"old": "1"}, tags={"old": "1"})
    session = DummySession(None, dedupe=existing)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    record, upload_url, ttl = await svc.create_upload_session(
        filename="a.txt",
        content_type="text/plain",
        size_bytes=1,
        metadata_json={"sha256": "b" * 64, "new": "2"},
    )
    assert record.id == "existing"
    assert upload_url == ""
    assert ttl == 0
    assert record.metadata_json["old"] == "1"
    assert record.metadata_json["new"] == "2"
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_signed_url_rejects_cross_tenant_object_key() -> None:
    rec = FileRecord(id="f1", tenant_id="t1", bucket="ptd", object_key="tenant-2/2026/03/03/f1/a.txt", content_type="text/plain", size_bytes=1, sha256="a" * 64, status=FileStatus.clean.value, av_result_json={}, metadata_json={})
    svc = FileService(session=DummySession(rec), tenant_id="t1")
    with pytest.raises(HTTPException) as exc:
        await svc.get_signed_download_url(file_id="f1", purpose="download")
    assert exc.value.status_code == 403
