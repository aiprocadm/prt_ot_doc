"""OPS-71 срез-9 (разд. 71.2): новые цели импорта — объекты и нормы СИЗ.

ТЗ прямо называет типовые структуры для переезда: «штатное расписание, списки
сотрудников, журналы, **нормы СИЗ**». Заодно это проверка обещания фреймворка:
новая сущность должна подключаться ЗАПИСЬЮ В РЕЕСТР, без процедурного кода.

Обещание подтвердилось частично — и это главный результат среза. Нормы СИЗ
висят на должности и организации не хранят, но НАЙТИ должность без организации
нельзя: одноимённые должности разных юрлиц — разные записи. Понадобилась
«прозрачная» колонка: значение участвует в поиске и ключе, но в модель не
пишется. Без неё организация уехала бы в конструктор `PPENorm` чужим аргументом.

Что закрепляется:

* объекты и нормы СИЗ загружаются и обновляются повторной загрузкой;
* **прозрачная колонка не протекает в модель** — иначе падение на создании;
* ключ норм совпадает с уникальным ключом таблицы, поэтому повторная загрузка
  обновляет норму, а не падает на UNIQUE;
* незнакомая опасность — обычная ошибка строки: справочник опасностей
  дозаведению не подлежит (это не название, а классифицированный фактор).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.master_data import Position, Site
from app.models.models import RoleEnum
from app.models.ppe import PPENorm
from app.models.risk import RiskHazard

API = "/api/v1/imports"


def _upload(body: str, name: str = "data.csv") -> dict:
    return {"file": (name, body.encode("utf-8"), "text/csv")}


@pytest.fixture()
async def tenant_with_catalog(sessionmaker, data_factory):
    """Арендатор с организацией, должностью и опасностью — нормы висят на них."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        session.add(Position(tenant_id=str(tenant.id), company_id=company.id, name="Слесарь"))
        session.add(RiskHazard(tenant_id=str(tenant.id), code="H-01", title="Шум", module="ot"))
        await session.commit()
        return tenant


async def _count(sessionmaker, model, tenant_id: str) -> int:
    async with sessionmaker() as session:
        stmt = select(func.count()).select_from(model).where(model.tenant_id == tenant_id)
        if hasattr(model, "deleted_at"):
            stmt = stmt.where(model.deleted_at.is_(None))
        return (await session.execute(stmt)).scalar_one()


@pytest.mark.anyio
class TestSitesTarget:
    async def test_sites_are_imported_and_reimport_is_idempotent(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = "Организация,Объект,Адрес\nАКМЕ,Цех №1,ул. Ленина 1\n"

        first = await async_client.post(f"{API}/sites/apply", files=_upload(body), headers=headers)
        second = await async_client.post(f"{API}/sites/apply", files=_upload(body), headers=headers)

        assert first.status_code == 201, first.text
        assert first.json()["batch"]["created_count"] == 1
        assert second.json()["batch"]["skipped_count"] == 1
        assert await _count(sessionmaker, Site, str(tenant_with_catalog.id)) == 1

    async def test_site_template_matches_autodetection(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        template = await async_client.get(f"{API}/targets/sites/template", headers=headers)
        header_line = template.text.strip().splitlines()[0].lstrip("﻿")

        preview = await async_client.post(
            f"{API}/sites/dry-run",
            files=_upload(header_line + "\nАКМЕ,Цех №1,,,,\n"),
            headers=headers,
        )

        assert preview.status_code == 200, preview.text
        assert preview.json()["counts"]["create"] == 1


@pytest.mark.anyio
class TestPpeNormsTarget:
    async def test_norm_is_imported_without_leaking_the_transient_column(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog, sessionmaker
    ) -> None:
        """Организация нужна для поиска должности, но в норме её нет."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = (
            "Организация,Должность,Опасность,Наименование СИЗ,Количество,Срок носки дней\n"
            "АКМЕ,Слесарь,Шум,Наушники противошумные,2,180\n"
        )

        response = await async_client.post(
            f"{API}/ppe_norms/apply", files=_upload(body), headers=headers
        )

        assert response.status_code == 201, response.text
        assert response.json()["batch"]["created_count"] == 1
        async with sessionmaker() as session:
            norm = (
                await session.execute(
                    select(PPENorm).where(PPENorm.tenant_id == str(tenant_with_catalog.id))
                )
            ).scalar_one()
        assert norm.item_name == "Наушники противошумные"
        assert (norm.quantity, norm.interval_days) == (2, 180)

    async def test_reimport_updates_the_norm_instead_of_hitting_unique(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        head = "Организация,Должность,Опасность,Наименование СИЗ,Количество,Срок носки дней\n"

        await async_client.post(
            f"{API}/ppe_norms/apply",
            files=_upload(head + "АКМЕ,Слесарь,Шум,Наушники,2,180\n"),
            headers=headers,
        )
        second = await async_client.post(
            f"{API}/ppe_norms/apply",
            files=_upload(head + "АКМЕ,Слесарь,Шум,Наушники,3,90\n"),
            headers=headers,
        )

        assert second.json()["batch"]["updated_count"] == 1
        assert await _count(sessionmaker, PPENorm, str(tenant_with_catalog.id)) == 1
        async with sessionmaker() as session:
            norm = (
                await session.execute(
                    select(PPENorm).where(PPENorm.tenant_id == str(tenant_with_catalog.id))
                )
            ).scalar_one()
        assert (norm.quantity, norm.interval_days) == (3, 90)

    async def test_unknown_hazard_is_a_row_error(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog
    ) -> None:
        """Опасность — классифицированный фактор, а не свободное название."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = (
            "Организация,Должность,Опасность,Наименование СИЗ\n"
            "АКМЕ,Слесарь,Неведомый фактор,Каска\n"
        )

        response = await async_client.post(
            f"{API}/ppe_norms/dry-run", files=_upload(body), headers=headers
        )

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["counts"]["error"] == 1
        assert payload["unknown_references"]["hazard"] == ["Неведомый фактор"]

    async def test_rollback_removes_imported_norms(
        self, async_client: AsyncClient, make_auth_headers, tenant_with_catalog, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = "Организация,Должность,Опасность,Наименование СИЗ\nАКМЕ,Слесарь,Шум,Каска\n"
        applied = await async_client.post(
            f"{API}/ppe_norms/apply", files=_upload(body), headers=headers
        )
        batch_id = applied.json()["batch"]["id"]

        rollback = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        assert rollback.status_code == 200, rollback.text
        assert await _count(sessionmaker, PPENorm, str(tenant_with_catalog.id)) == 0


@pytest.mark.anyio
async def test_new_targets_are_listed(
    async_client: AsyncClient, make_auth_headers, tenant_with_catalog
) -> None:
    response = await async_client.get(
        f"{API}/targets", headers=await make_auth_headers(RoleEnum.ADMIN)
    )

    codes = {t["code"] for t in response.json()}
    assert {"positions", "persons", "sites", "ppe_norms"} <= codes
