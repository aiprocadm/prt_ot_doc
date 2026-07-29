"""OPS-72 (разд. 72.2): полный экспорт данных арендатора.

ТЗ: «ПОЛНЫЙ дамп данных арендатора для переезда», «структурированный формат со
схемой», «самообслуживание», «аудит экспорта».

Что здесь закрепляется:

* **состав дампа берётся из реестра RLS** — «полный» экспорт со списком таблиц
  вручную устаревает в первый же спринт и молча отдаёт клиенту неполные данные;
  реестр же стережёт CI-гард, и новая tenant-таблица не пройдёт сборку, пока в
  него не попадёт;
* **дамп содержит только данные своего арендатора** — экспорт, отдающий чужие
  строки, это утечка под видом полезной функции;
* **усечение видно в манифесте** — молча обрезанный экспорт хуже отказа: клиент
  переедет с неполными данными и узнает об этом у нового поставщика;
* доступ только у `owner`/`admin`: полный дамп — это все ПДн арендатора разом.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.modules.offboarding.export import (
    EXPORT_FORMAT_VERSION,
    TenantExportService,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def test_export_scope_comes_from_the_rls_registry() -> None:
    """Список таблиц не дублируется руками — иначе он разъедется с реальностью."""

    from app.core.rls_policy import RLS_ENABLED_TABLES, RLS_EXEMPT_TABLES

    tables = TenantExportService.exportable_tables()

    assert set(tables) == set(RLS_ENABLED_TABLES)
    assert tables == sorted(tables), "порядок стабилен — дампы сравнимы между собой"
    # Единственное исключение реестра — платформенный справочник прав, это не
    # данные арендатора и в его выгрузке ему делать нечего.
    assert not (set(tables) & set(RLS_EXEMPT_TABLES))
    assert len(tables) > 200, f"подозрительно мало таблиц в составе дампа: {len(tables)}"


@pytest.mark.anyio
class TestExportContent:
    async def test_dump_contains_own_rows_with_schema(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="export-a", session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        await data_factory.create_person(
            tenant=tenant, company=company, session=test_db_session, first_name="Экспорт"
        )
        await test_db_session.commit()

        manifest = await TenantExportService(
            test_db_session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
        ).build(include_rows=True)

        assert manifest.format_version == EXPORT_FORMAT_VERSION
        assert manifest.tenant_slug == "export-a"
        by_table = {dump.table: dump for dump in manifest.tables}
        assert "person" in by_table, "сотрудники обязаны попасть в дамп"
        person_dump = by_table["person"]
        assert person_dump.row_count >= 1
        # Схема рядом с данными: принимающая система должна понять дамп без нас.
        assert "first_name" in person_dump.columns
        assert any(row.get("first_name") == "Экспорт" for row in person_dump.rows)

    async def test_dump_is_isolated_between_tenants(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Экспорт, отдающий чужие строки, — утечка под видом полезной функции."""

        tenant_a = await data_factory.ensure_tenant(slug="export-b", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="export-c", session=test_db_session)
        company = await data_factory.create_company(tenant=tenant_a, session=test_db_session)
        await data_factory.create_person(
            tenant=tenant_a, company=company, session=test_db_session, first_name="Чужой"
        )
        await test_db_session.commit()

        manifest = await TenantExportService(
            test_db_session, tenant_id=str(tenant_b.id), tenant_slug=tenant_b.slug
        ).build(include_rows=True)

        for dump in manifest.tables:
            for row in dump.rows:
                assert row.get("tenant_id") in (None, str(tenant_b.id)), dump.table
        assert not any(
            row.get("first_name") == "Чужой" for dump in manifest.tables for row in dump.rows
        )

    async def test_truncation_is_visible_in_the_manifest(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Молча обрезанный экспорт хуже отказа: клиент переедет неполным."""

        tenant = await data_factory.ensure_tenant(slug="export-d", session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        for index in range(3):
            await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=test_db_session,
                first_name=f"Сотрудник{index}",
            )
        await test_db_session.commit()

        manifest = await TenantExportService(
            test_db_session,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
            rows_per_table=1,
        ).build(include_rows=True)

        person_dump = next(d for d in manifest.tables if d.table == "person")
        assert person_dump.truncated is True
        assert person_dump.exported_rows == 1
        assert person_dump.row_count >= 3
        assert manifest.truncated is True

    async def test_empty_tables_are_omitted(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Дамп из 276 пустых секций нечитаем; пустое просто не попадает в манифест."""

        tenant = await data_factory.ensure_tenant(slug="export-e", session=test_db_session)
        await test_db_session.commit()

        manifest = await TenantExportService(
            test_db_session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
        ).build(include_rows=True)

        assert all(dump.row_count > 0 for dump in manifest.tables)

    async def test_files_are_referenced_not_copied(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Синхронная выгрузка гигабайтов обрушила бы запрос — отдаём префикс."""

        tenant = await data_factory.ensure_tenant(slug="export-f", session=test_db_session)
        await test_db_session.commit()

        manifest = await TenantExportService(
            test_db_session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
        ).build(include_rows=False)

        assert manifest.files_prefix == "tenants/export-f/"


@pytest.mark.anyio
class TestExportEndpoints:
    async def test_manifest_endpoint_reports_volume_without_rows(
        self, async_client, make_auth_headers
    ) -> None:
        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export/manifest",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format_version"] == EXPORT_FORMAT_VERSION
        assert "tables" in body
        # Лёгкая ручка: объём виден, строк нет.
        assert all("rows" not in table for table in body["tables"])

    async def test_full_export_returns_rows(self, async_client, make_auth_headers) -> None:
        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["format_version"] == EXPORT_FORMAT_VERSION
        assert all("rows" in table for table in body["tables"])

    async def test_line_manager_cannot_export_everything(
        self, async_client, make_auth_headers
    ) -> None:
        """Полный дамп — все ПДн разом; линейным ролям он недоступен."""

        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export",
            headers=await make_auth_headers(RoleEnum.LINE_MANAGER),
        )
        assert response.status_code == 403, response.text
