from __future__ import annotations

import io
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

from app.api.routes import files as legacy_files_api
from app.modules.files import api as files_api
from app.modules.files.schemas import SignedUrlRequest
from app.modules.files.service import FileService, _safe_filename


class _FakeSession:
    def __init__(self, record) -> None:
        self._record = record
        self.added: list[object] = []

    async def get(self, _model, _id):  # noqa: ANN001
        return self._record

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def execute(self, *_args, **_kwargs):  # noqa: ANN001
        class _Result:
            @staticmethod
            def scalar_one_or_none():
                return None

        return _Result()


class _AccessStub:
    def __init__(self, *, role: str, company_id: str | None) -> None:
        self.role = role
        self.company_id = company_id

    def ensure_company_access(self, company_id: str | None, *, action: str = "access company resource") -> None:
        if self.company_id is None or company_id is None or str(company_id) != str(self.company_id):
            raise HTTPException(status_code=403, detail=f"Company mismatch for {action}")


def test_ingest_upload_rejects_mime_extension_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    async_file = UploadFile(
        file=io.BytesIO(b"%PDF-1.4\n"),
        filename="invoice.exe",
        headers={"content-type": "application/pdf"},
    )
    monkeypatch.setattr(legacy_files_api, "guess_mime_type", lambda **_kwargs: "application/pdf")
    monkeypatch.setattr(
        legacy_files_api,
        "determine_extension",
        lambda filename, mime: "exe" if filename else "pdf",
    )

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await legacy_files_api._ingest_upload(
                file=async_file,
                limit=1024 * 1024,
                allowed_mimes={"application/pdf"},
                allowed_extensions={"pdf"},
            )
        assert exc.value.status_code == 400
        assert exc.value.detail["code"] == "FILE_EXTENSION_MISMATCH"

    asyncio.run(_run())


def test_safe_filename_strips_traversal_tokens() -> None:
    safe = _safe_filename("../../etc/passwd")
    assert "/" not in safe
    assert ".." not in safe
    assert safe.endswith("etc_passwd")


def test_signed_url_request_rejects_ttl_below_floor() -> None:
    with pytest.raises(ValidationError):
        SignedUrlRequest(action="download", ttl_seconds=5)


def test_get_signed_download_url_rejects_cross_tenant_access() -> None:
    record = SimpleNamespace(id="file-1", tenant_id="tenant-b", status="clean", object_key="tenants/tenant-b/files/a")
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.get_signed_download_url(file_id="file-1", purpose="download")
        assert exc.value.status_code == 404
        assert exc.value.detail == "file_not_found"

    asyncio.run(_run())


def test_get_signed_download_url_rejects_non_clean_file() -> None:
    record = SimpleNamespace(id="file-1", tenant_id="tenant-a", status="infected", object_key="tenants/tenant-a/files/a")
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.get_signed_download_url(file_id="file-1", purpose="download")
        assert exc.value.status_code == 403
        assert exc.value.detail == "file_not_clean"

    asyncio.run(_run())


def test_get_signed_download_url_rejects_cross_company_client_access() -> None:
    record = SimpleNamespace(
        id="file-1",
        tenant_id="tenant-a",
        status="clean",
        object_key="tenants/tenant-a/files/a",
        metadata_json={"company_id": "company-a"},
        tags={},
    )
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")
    access = _AccessStub(role="client_user", company_id="company-b")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.get_signed_download_url(file_id="file-1", purpose="download", access=access)
        assert exc.value.status_code == 403
        assert exc.value.detail == "forbidden"

    asyncio.run(_run())


def test_delete_file_rejects_cross_tenant_access() -> None:
    record = SimpleNamespace(id="file-1", tenant_id="tenant-b")
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.delete_file(file_id="file-1")
        assert exc.value.status_code == 404
        assert exc.value.detail == "file_not_found"

    asyncio.run(_run())


def test_delete_file_rejects_cross_company_client_access() -> None:
    record = SimpleNamespace(
        id="file-1",
        tenant_id="tenant-a",
        metadata_json={"company_id": "company-a"},
        tags={},
    )
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")
    access = _AccessStub(role="client_admin", company_id="company-b")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.delete_file(file_id="file-1", access=access)
        assert exc.value.status_code == 403
        assert exc.value.detail == "forbidden"

    asyncio.run(_run())


def test_create_upload_session_rejects_dangerous_double_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        max_upload_size=10 * 1024 * 1024,
        file_allowed_mime={"application/pdf"},
        file_allowed_extensions={"pdf"},
        presign_download_ttl_seconds=600,
    )
    monkeypatch.setattr("app.modules.files.service.get_settings", lambda: settings)
    svc = FileService(session=_FakeSession(record=None), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.create_upload_session(
                filename="statement.pdf.exe",
                content_type="application/pdf",
                size_bytes=32,
                metadata_json=None,
            )
        assert exc.value.status_code == 400
        assert exc.value.detail == "dangerous_double_extension"

    asyncio.run(_run())


def test_get_signed_download_url_rejects_client_user_from_foreign_company() -> None:
    record = SimpleNamespace(
        id="file-1",
        tenant_id="tenant-a",
        status="clean",
        object_key="tenants/tenant-a/files/a",
        metadata_json={"company_id": "company-b"},
        tags={},
    )
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.get_signed_download_url(
                file_id="file-1",
                purpose="download",
                actor_role="client_user",
                actor_company_id="company-a",
            )
        assert exc.value.status_code == 403
        assert exc.value.detail == "file_company_forbidden"

    asyncio.run(_run())


def test_get_signed_download_url_rejects_cross_tenant_even_for_client_role() -> None:
    record = SimpleNamespace(
        id="file-1",
        tenant_id="tenant-b",
        status="clean",
        object_key="tenants/tenant-b/files/a",
        metadata_json={"company_id": "company-a"},
        tags={},
    )
    svc = FileService(session=_FakeSession(record), tenant_id="tenant-a")

    async def _run() -> None:
        with pytest.raises(HTTPException) as exc:
            await svc.get_signed_download_url(
                file_id="file-1",
                purpose="download",
                actor_role="client_user",
                actor_company_id="company-a",
            )
        assert exc.value.status_code == 404
        assert exc.value.detail == "file_not_found"

    asyncio.run(_run())


def test_route_guard_rejects_stale_role_downgrade() -> None:
    stale_access = SimpleNamespace(role="client_user")
    with pytest.raises(HTTPException) as exc:
        files_api._enforce_access_role(stale_access, files_api._FILE_UPLOAD_ROLES)
    assert exc.value.status_code == 403
    assert exc.value.detail == "insufficient_role"
