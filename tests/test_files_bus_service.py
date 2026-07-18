from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.files.models import FileDownloadLog, FileLink, FileRecord, FileStatus
from app.modules.files.service import FileService, compute_sha256_stream


class _NullResult:
    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return None

    def scalars(self):
        return self

    def all(self):
        return []


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
        return _NullResult()


class DummyAccess:
    def __init__(self, *, role: str, company_id: str | None) -> None:
        self.role = role
        self.company_id = company_id

    def ensure_company_access(self, company_id: str | None, *, action: str = "access") -> None:
        if company_id is None or self.company_id is None or str(company_id) != str(self.company_id):
            raise HTTPException(status_code=403, detail=f"forbidden:{action}")


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (
            [b"hello", b" ", b"world"],
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        )
    ],
)
def test_compute_sha256_stream(chunks: list[bytes], expected: str) -> None:
    assert compute_sha256_stream(chunks) == expected


@pytest.mark.asyncio
async def test_download_blocked_if_not_clean() -> None:
    rec = FileRecord(
        id="f1",
        tenant_id="t1",
        bucket="main",
        object_key="a",
        content_type="text/plain",
        size_bytes=1,
        sha256="a" * 64,
        status=FileStatus.scanning.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    with pytest.raises(HTTPException) as exc:
        await svc.get_signed_download_url(file_id="f1", purpose="api")

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_link_and_unlink_file() -> None:
    rec = FileRecord(
        id="f2",
        tenant_id="t1",
        bucket="main",
        object_key="a",
        content_type="text/plain",
        size_bytes=1,
        sha256="b" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={},
    )
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
    rec = FileRecord(
        id="f3",
        tenant_id="t1",
        bucket="main",
        object_key="k",
        content_type="text/plain",
        size_bytes=1,
        sha256="c" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setattr(
        "app.modules.files.storage.presign_get", lambda *, key, expires_in: "http://signed"
    )
    url = await svc.get_signed_download_url(
        file_id="f3", purpose="ui_preview", ip="127.0.0.1", user_agent="pytest"
    )

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

    rec = FileRecord(
        id="f4",
        tenant_id="t1",
        bucket="main",
        object_key="a",
        content_type="text/plain",
        size_bytes=1,
        sha256="d" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("MAX_UPLOAD_SIZE", "10")
    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(HTTPException) as exc:
        await svc.create_upload_session(filename="a.txt", content_type="text/plain", size_bytes=11)

    assert exc.value.status_code == 413

    with pytest.raises(HTTPException) as exc2:
        await svc.create_upload_session(
            filename="a.pdf", content_type="application/pdf", size_bytes=5
        )

    assert exc2.value.status_code == 415

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_create_upload_session_uses_tenant_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    session = DummySession(None)
    svc = FileService(session=session, tenant_id="tenant-xyz")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "app.modules.files.service.s3.generate_presigned_put_url",
        lambda key, **kwargs: "http://put",
    )
    rec, _url, _ttl = await svc.create_upload_session(
        filename="a.txt", content_type="text/plain", size_bytes=1
    )
    assert rec.object_key.startswith("tenants/tenant-xyz/")
    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_av_scan_infected_moves_to_quarantine(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FileRecord(
        id="f5",
        tenant_id="t1",
        bucket="main",
        object_key="tenant/t1/uploads/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="e" * 64,
        status=FileStatus.scanning.value,
        av_result_json={},
        metadata_json={},
    )
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

    assert rec.status == FileStatus.infected.value


@pytest.mark.asyncio
async def test_finalize_upload_emits_file_uploaded_event(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FileRecord(
        id="f7",
        tenant_id="t1",
        bucket="main",
        object_key="tenant/t1/uploads/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="0" * 64,
        status=FileStatus.uploaded.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")
    events: list[str] = []

    class _Body:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"safe"

    monkeypatch.setattr(
        "app.modules.files.service.s3.head_object",
        lambda *, key: {"size": 4, "content_type": "text/plain"},
    )
    monkeypatch.setattr("app.modules.files.service.s3.stream_object", lambda *, key: _Body())
    monkeypatch.setattr("app.modules.files.service.av_scan_file_job.delay", lambda *_args: None)

    async def _capture_event(self, *, event_type, **kwargs):  # type: ignore[no-untyped-def]
        events.append(event_type)
        return None

    monkeypatch.setattr("app.modules.files.service.OutboxService.add_event", _capture_event)

    await svc.finalize_upload(file_id="f7")

    assert "FileUploaded" in events


@pytest.mark.asyncio
async def test_av_scan_error_creates_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    rec = FileRecord(
        id="f8",
        tenant_id="t1",
        bucket="main",
        object_key="tenant/t1/uploads/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="1" * 64,
        status=FileStatus.scanning.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    class _Body:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"safe"

    def _broken_scan(_path):  # type: ignore[no-untyped-def]
        raise RuntimeError("clamd_down")

    monkeypatch.setattr("app.modules.files.service.s3.stream_object", lambda *, key: _Body())
    monkeypatch.setattr("app.modules.files.service.av.scan_file", _broken_scan)

    await svc.av_scan_file(file_id="f8")

    assert rec.status == FileStatus.scanning.value
    assert rec.av_result_json.get("status") == "error"


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class DummySessionWithVersion(DummySession):
    async def execute(self, stmt):
        return _ScalarResult(2)


@pytest.mark.asyncio
async def test_create_new_version_upload_session_uses_tenant_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import get_settings
    from app.modules.files.models import FileVersion

    rec = FileRecord(
        id="f6",
        tenant_id="t1",
        bucket="main",
        object_key="tenant/t1/uploads/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="f" * 64,
        status=FileStatus.ready.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySessionWithVersion(rec)
    svc = FileService(session=session, tenant_id="t1")

    monkeypatch.setenv("FILE_ALLOWED_MIME", "text/plain")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        "app.modules.files.service.s3.generate_presigned_put_url",
        lambda key, **kwargs: f"http://put/{key}",
    )

    version, upload_url, _ = await svc.create_new_version_upload_session(
        file_id="f6", filename="next.txt", content_type="text/plain", size_bytes=10
    )

    assert isinstance(version, FileVersion)
    assert version.version_no == 3
    assert version.s3_key.startswith("tenants/t1/files/f6/f6/v3/")
    assert upload_url.startswith("http://put/tenants/t1/files/f6/f6/v3/")
    get_settings.cache_clear()  # type: ignore[attr-defined]


def test_mask_pii_for_indexing() -> None:
    from app.modules.files.service import _mask_pii

    text = "mail a@b.com phone +7 (999) 123-45-67 passport 1234 567890"
    masked = _mask_pii(text)
    assert "a@b.com" not in masked
    assert "1234 567890" not in masked
    assert "[masked_email]" in masked


@pytest.mark.asyncio
async def test_link_output_requires_clean() -> None:
    rec = FileRecord(
        id="f9",
        tenant_id="t1",
        bucket="main",
        object_key="a",
        content_type="text/plain",
        size_bytes=1,
        sha256="f" * 64,
        status=FileStatus.scanning.value,
        av_result_json={},
        metadata_json={},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")

    with pytest.raises(HTTPException) as exc:
        await svc.link_file(file_id="f9", entity_type="job", entity_id="j1", role="output")

    assert exc.value.status_code == 403


def test_extract_company_id_from_metadata_or_tags() -> None:
    record_from_meta = FileRecord(
        id="fm",
        tenant_id="t1",
        bucket="main",
        object_key="k",
        content_type="text/plain",
        size_bytes=1,
        sha256="a" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={"company_id": "c-meta"},
        tags={"company_id": "c-tag"},
    )
    record_from_tags = FileRecord(
        id="ft",
        tenant_id="t1",
        bucket="main",
        object_key="k",
        content_type="text/plain",
        size_bytes=1,
        sha256="b" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={},
        tags={"company_id": "c-tag"},
    )
    assert FileService._extract_company_id(record_from_meta) == "c-meta"
    assert FileService._extract_company_id(record_from_tags) == "c-tag"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["client_admin", "client_user"])
async def test_client_roles_company_scope_allow_and_deny_on_download(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = FileRecord(
        id="f10",
        tenant_id="t1",
        bucket="main",
        object_key="tenants/t1/files/f10/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="c" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={"company_id": "cmp-1"},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")
    audits: list[str] = []
    monkeypatch.setattr(
        "app.modules.files.storage.presign_get", lambda *, key, expires_in: "http://signed"
    )

    async def _audit_capture(self, **kwargs):  # type: ignore[no-untyped-def]
        audits.append(kwargs["action"])

    monkeypatch.setattr("app.modules.files.service.FileService._audit_file_action", _audit_capture)

    url = await svc.get_signed_download_url(
        file_id="f10",
        purpose="api",
        actor_role=role,
        actor_company_id="cmp-1",
        access=DummyAccess(role=role, company_id="cmp-1"),
    )
    assert url == "http://signed"

    with pytest.raises(HTTPException) as exc:
        await svc.get_signed_download_url(
            file_id="f10",
            purpose="api",
            actor_role=role,
            actor_company_id="cmp-2",
            actor_id="u1",
            access=DummyAccess(role=role, company_id="cmp-2"),
        )
    assert exc.value.status_code == 403
    assert "file.download_url.denied" in audits


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["client_admin", "client_user"])
async def test_client_roles_company_scope_allow_and_deny_on_delete(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = FileRecord(
        id="f11",
        tenant_id="t1",
        bucket="main",
        object_key="k",
        content_type="text/plain",
        size_bytes=1,
        sha256="d" * 64,
        status=FileStatus.clean.value,
        av_result_json={},
        metadata_json={"company_id": "cmp-1"},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")
    audits: list[str] = []

    async def _audit_capture(self, **kwargs):  # type: ignore[no-untyped-def]
        audits.append(kwargs["action"])

    monkeypatch.setattr("app.modules.files.service.FileService._audit_file_action", _audit_capture)
    deleted = await svc.delete_file(
        file_id="f11",
        actor_role=role,
        actor_company_id="cmp-1",
        access=DummyAccess(role=role, company_id="cmp-1"),
    )
    assert deleted.status == FileStatus.deleted.value

    rec.status = FileStatus.clean.value
    rec.deleted_at = None
    with pytest.raises(HTTPException) as exc:
        await svc.delete_file(
            file_id="f11",
            actor_id="u1",
            actor_role=role,
            actor_company_id="cmp-2",
            access=DummyAccess(role=role, company_id="cmp-2"),
        )
    assert exc.value.status_code == 403
    assert "file.delete.denied" in audits


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["client_admin", "client_user"])
async def test_client_roles_company_scope_deny_on_finalize_and_link(
    role: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = FileRecord(
        id="f12",
        tenant_id="t1",
        bucket="main",
        object_key="tenant/t1/uploads/a.txt",
        content_type="text/plain",
        size_bytes=1,
        sha256="e" * 64,
        status=FileStatus.uploaded.value,
        av_result_json={},
        metadata_json={"company_id": "cmp-1"},
    )
    session = DummySession(rec)
    svc = FileService(session=session, tenant_id="t1")
    audits: list[str] = []

    async def _audit_capture(self, **kwargs):  # type: ignore[no-untyped-def]
        audits.append(kwargs["action"])

    monkeypatch.setattr("app.modules.files.service.FileService._audit_file_action", _audit_capture)

    with pytest.raises(HTTPException):
        await svc.finalize_upload(
            file_id="f12",
            actor_id="u1",
            actor_role=role,
            actor_company_id="cmp-2",
        )
    with pytest.raises(HTTPException):
        await svc.link_file(
            file_id="f12",
            entity_type="job",
            entity_id="j1",
            role="artifact",
            actor_id="u1",
            actor_role=role,
            actor_company_id="cmp-2",
            access=DummyAccess(role=role, company_id="cmp-2"),
        )

    assert "file.finalize.denied" in audits
    assert "file.link.denied" in audits
