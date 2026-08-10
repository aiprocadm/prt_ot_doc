"""OPS-71 срез-6 (разд. 71.3): дозаведение справочников из импорта и отчёт файлом.

ТЗ: «Маппинг на справочники: незнакомые значения (должность, которой нет в
справочнике) — предложить создать или сопоставить, а не молча пропустить» и
«Отчёт об импорте … скачиваемый, с привязкой к batch id для отката».

Что закрепляется:

* по умолчанию поведение НЕ меняется — незнакомое значение по-прежнему ошибка
  строки: тихое создание записей справочника «за спиной» хуже отказа;
* дозавести можно только то, что реестр пометил как разрешённое: организация
  несёт реквизиты, и автосоздание юрлица из опечатки засорило бы справочник;
* **созданные записи справочника снимаются откатом партии** — иначе после
  отмены загрузки в справочнике остаётся мусор, который никто с ней не свяжет;
* откат идёт в правильном порядке: сотрудник ссылается на созданную должность,
  и обратный порядок упёрся бы в этот внешний ключ;
* отчёт скачивается файлом и различает строки файла и записи справочника.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.master_data import Person, Position
from app.models.models import RoleEnum

API = "/api/v1/imports"
HEADER = "Организация,Фамилия,Имя,Табельный номер,Должность\n"


def _csv(*rows: str) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        await session.commit()
        return tenant


async def _count(sessionmaker, model, tenant_id: str) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id, model.deleted_at.is_(None))
            )
        ).scalar_one()


@pytest.mark.anyio
class TestCreateMissingReferences:
    async def test_unknown_position_is_still_an_error_by_default(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        """Тихое создание записей «за спиной» хуже отказа — поведение по умолчанию."""

        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,Слесарь\n")),
            headers=headers,
        )

        assert response.status_code == 201, response.text
        assert response.json()["batch"]["failed_count"] == 1
        assert await _count(sessionmaker, Position, str(imports_tenant.id)) == 0

    async def test_opt_in_creates_the_position_and_imports_the_row(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,Слесарь\n")),
            data={"create_missing": "position"},
            headers=headers,
        )

        assert response.status_code == 201, response.text
        batch = response.json()["batch"]
        # Сотрудник + должность: обе записи создала эта партия.
        assert batch["created_count"] == 2
        assert batch["failed_count"] == 0
        assert batch["notes"]["created_references"] == [{"lookup": "position", "value": "Слесарь"}]
        assert await _count(sessionmaker, Position, str(imports_tenant.id)) == 1
        assert await _count(sessionmaker, Person, str(imports_tenant.id)) == 1

    async def test_company_cannot_be_created_from_an_import(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        """Юрлицо несёт реквизиты — заводить его из опечатки в файле нельзя."""

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("НЕТ ТАКОЙ,Иванов,Иван,001,Слесарь\n")),
            data={"create_missing": "company"},
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "IMPORT_LOOKUP_NOT_CREATABLE"
        assert detail["creatable_lookups"] == ["position"]

    async def test_created_reference_is_removed_by_rollback(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        """Справочная запись, пережившая откат, — мусор, который уже никто не свяжет."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        applied = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,Слесарь\n")),
            data={"create_missing": "position"},
            headers=headers,
        )
        batch_id = applied.json()["batch"]["id"]
        assert await _count(sessionmaker, Position, str(imports_tenant.id)) == 1

        rollback = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        assert rollback.status_code == 200, rollback.text
        # Порядок удаления важен: сотрудник ссылается на созданную должность.
        assert await _count(sessionmaker, Person, str(imports_tenant.id)) == 0
        assert await _count(sessionmaker, Position, str(imports_tenant.id)) == 0

    async def test_existing_position_is_reused_not_duplicated(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        sessionmaker,
        data_factory,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        async with sessionmaker() as session:
            company = (
                await session.execute(select(Position.company_id).limit(1))
            ).scalar_one_or_none()
            from app.models.master_data import Company

            company_id = (
                company
                or (
                    await session.execute(
                        select(Company.id).where(Company.tenant_id == str(imports_tenant.id))
                    )
                ).scalar_one()
            )
            session.add(
                Position(tenant_id=str(imports_tenant.id), company_id=company_id, name="Слесарь")
            )
            await session.commit()

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,Слесарь\n")),
            data={"create_missing": "position"},
            headers=headers,
        )

        assert response.json()["batch"]["created_count"] == 1  # только сотрудник
        assert await _count(sessionmaker, Position, str(imports_tenant.id)) == 1

    async def test_targets_tell_the_client_what_can_be_created(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        targets = await async_client.get(
            f"{API}/targets", headers=await make_auth_headers(RoleEnum.ADMIN)
        )

        persons = next(t for t in targets.json() if t["code"] == "persons")
        by_field = {c["field"]: c for c in persons["columns"]}
        assert by_field["position_id"]["lookup_creatable"] is True
        assert by_field["company_id"]["lookup_creatable"] is False


@pytest.mark.anyio
class TestBatchReport:
    async def test_report_is_downloadable_and_marks_reference_rows(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        applied = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(
                "Организация,Фамилия,Имя,Табельный номер,Должность\nАКМЕ,Иванов,Иван,001,Слесарь\nАКМЕ,,Пётр,002,\n".encode(
                    "utf-8"
                )
            ),
            data={"create_missing": "position"},
            headers=headers,
        )
        batch_id = applied.json()["batch"]["id"]

        report = await async_client.get(f"{API}/batches/{batch_id}/report", headers=headers)

        assert report.status_code == 200, report.text
        assert "attachment" in report.headers["content-disposition"]
        body = report.text
        assert body.startswith("﻿")
        assert "Строка;Действие" in body
        # Дозаведённая должность — не строка файла, и в отчёте это видно словом.
        assert "справочник" in body
        assert "failed" in body

    async def test_report_of_unknown_batch_is_404(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.get(
            f"{API}/batches/00000000-0000-0000-0000-000000000000/report",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 404
