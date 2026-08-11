"""OPS-72 срез-4 (разд. 72.2): файлы арендатора архивом.

Срез-1 отдавал только префикс хранилища — «файлы архивом» из ТЗ оставались
невыполненными. Что закрепляется здесь:

* **состав архива = состав удаления** (общий сборщик ключей): разойдись эти два
  списка, клиент получил бы в архиве меньше, чем у него стёрли, и узнал бы об
  этом уже у нового поставщика;
* **усечение видно ВНУТРИ архива** (``MANIFEST.json``) и в заголовке ответа:
  молча обрезанный архив хуже отказа, потому что выглядит как успех;
* **один битый объект не лишает клиента остальных файлов**, но и не исчезает
  молча — попадает в манифест;
* **чужие файлы в архив не попадают** — та же изоляция, что и везде.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.modules.offboarding.files_archive import (
    ARCHIVE_MANIFEST_NAME,
    TenantFilesArchiveService,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


class _FakeStorage:
    """Хранилище-заглушка: отдаёт байты по ключу, на одном ключе падает."""

    def __init__(self, blobs: dict[str, bytes], *, unreadable: str | None = None) -> None:
        self.blobs = blobs
        self.unreadable = unreadable

    def get(self, key: str) -> bytes:
        if key == self.unreadable:
            raise RuntimeError("объект недоступен")
        return self.blobs[key]


async def _document_with_files(
    data_factory: TestDataFactory, session: AsyncSession, slug: str, keys: list[str]
):
    tenant = await data_factory.ensure_tenant(slug=slug, session=session)
    await data_factory.create_document(tenant=tenant, session=session)
    # Фабрика кладёт свой ключ в версию документа; сводим оба места к одному
    # известному ключу, иначе тест проверял бы фабрику, а не выгрузку.
    await session.execute(
        text("UPDATE document SET storage_key = :key WHERE tenant_id = :tenant"),
        {"key": keys[0], "tenant": str(tenant.id)},
    )
    await session.execute(
        text("UPDATE documentversion SET file_key = :key WHERE tenant_id = :tenant"),
        {"key": keys[0], "tenant": str(tenant.id)},
    )
    await session.commit()
    return tenant


@pytest.mark.anyio
class TestFilesArchive:
    async def test_archive_contains_tenant_files_and_a_manifest(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        key = "tenants/arch-a/doc.pdf"
        tenant = await _document_with_files(data_factory, test_db_session, "arch-a", [key])
        service = TenantFilesArchiveService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            storage=_FakeStorage({key: b"PDF-CONTENT"}),
        )

        payload, report = await service.build()

        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            assert ARCHIVE_MANIFEST_NAME in names
            assert f"files/{key}" in names
            assert archive.read(f"files/{key}") == b"PDF-CONTENT"
            manifest = json.loads(archive.read(ARCHIVE_MANIFEST_NAME))
        assert manifest["included_files"] == 1
        assert manifest["truncated"] is False
        assert report.total_bytes == len(b"PDF-CONTENT")

    async def test_unreadable_object_is_reported_not_swallowed(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        key = "tenants/arch-b/broken.pdf"
        tenant = await _document_with_files(data_factory, test_db_session, "arch-b", [key])
        service = TenantFilesArchiveService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            storage=_FakeStorage({}, unreadable=key),
        )

        payload, report = await service.build()

        assert report.included == []
        assert report.skipped == [{"key": key, "reason": "unreadable"}]
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read(ARCHIVE_MANIFEST_NAME))
        assert manifest["truncated"] is True

    async def test_size_cap_truncates_visibly(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Потолок обязателен, но клиент обязан узнать, что получил не всё."""

        key = "tenants/arch-c/big.pdf"
        tenant = await _document_with_files(data_factory, test_db_session, "arch-c", [key])
        service = TenantFilesArchiveService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            storage=_FakeStorage({key: b"x" * 100}),
            max_bytes=10,
        )

        _, report = await service.build()

        assert report.included == []
        assert report.skipped == [{"key": key, "reason": "max_bytes"}]
        assert report.truncated is True

    async def test_another_tenants_files_are_not_included(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        mine = "tenants/arch-d/mine.pdf"
        theirs = "tenants/arch-d-next/theirs.pdf"
        tenant = await _document_with_files(data_factory, test_db_session, "arch-d", [mine])
        await _document_with_files(data_factory, test_db_session, "arch-d-next", [theirs])
        service = TenantFilesArchiveService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            storage=_FakeStorage({mine: b"A", theirs: b"B"}),
        )

        _, report = await service.build()

        assert [item["key"] for item in report.included] == [mine]

    async def test_archive_keys_match_the_purge_collector(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Архив и удаление обязаны видеть ОДИН набор файлов."""

        from app.core.rls_policy import RLS_ENABLED_TABLES
        from app.modules.offboarding.file_keys import collect_file_keys

        key = "tenants/arch-e/doc.pdf"
        tenant = await _document_with_files(data_factory, test_db_session, "arch-e", [key])
        service = TenantFilesArchiveService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            storage=_FakeStorage({key: b"A"}),
        )

        assert await service.keys() == await collect_file_keys(
            test_db_session, RLS_ENABLED_TABLES, tenant_id=str(tenant.id)
        )


@pytest.mark.anyio
class TestFilesArchiveEndpoint:
    async def test_endpoint_returns_a_zip(self, async_client, make_auth_headers) -> None:
        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export/files",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["x-export-truncated"] == "false"
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert ARCHIVE_MANIFEST_NAME in archive.namelist()

    async def test_endpoint_is_closed_for_line_manager(
        self, async_client, make_auth_headers
    ) -> None:
        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export/files",
            headers=await make_auth_headers(RoleEnum.LINE_MANAGER),
        )
        assert response.status_code == 403, response.text
