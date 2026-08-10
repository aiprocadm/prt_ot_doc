"""OPS-71 срез-1 (разд. 71.1): импорт-фреймворк через API — полный цикл.

Что закрепляется:

* модуль за флагом ``imports`` default-OFF: импорт пишет в кадровые таблицы;
* шаблон скачивается и его заголовки понимает автоопределение — иначе
  пользователь заполняет наш же шаблон и получает «нет обязательной колонки»;
* dry-run НЕ пишет в БД (разд. 71.1 требует именно этого);
* применение импортирует корректные строки и откладывает ошибочные
  («частичный импорт», а не падение файла целиком);
* **повторная загрузка того же файла ничего не создаёт** — идемпотентность;
* **откат партии** удаляет созданное и ВОЗВРАЩАЕТ перезаписанное; повторный
  откат отвергается 409, а не делает вид, что сработал.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.master_data import Person
from app.models.models import RoleEnum, Tenant

API = "/api/v1/imports"

HEADER_LINE = "Организация,Фамилия,Имя,Табельный номер,Дата рождения\n"


def _csv(*rows: str) -> bytes:
    return (HEADER_LINE + "".join(rows)).encode("utf-8")


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    """Арендатор с одной организацией.

    Выдавать модуль больше не нужно: импорт — ядро (решение владельца
    2026-08-08), он доступен любому арендатору.
    """

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        await session.commit()
        return str(tenant.id)


async def _count_persons(sessionmaker, tenant_id: str) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None))
            )
        ).scalar_one()


@pytest.mark.anyio
class TestFeatureGate:
    """Импорт — ядро: доступен без выдачи, но гейт остаётся живым."""

    async def test_import_works_without_any_grant(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        """Ровно то, что было сломано: модуль отвечал «не найдено» ВСЕМ.

        Строку о выдаче с кодом ``imports`` создать было нечем — кода не было
        ни в каталоге, ни в тарифах. При этом пункт меню «Импорт данных» видели
        владелец и админ любого арендатора.
        """

        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(f"{API}/targets", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json(), "список видов загрузки пуст — импортировать нечего"

    async def test_explicit_off_row_still_closes_the_module(
        self, async_client: AsyncClient, make_auth_headers, sessionmaker
    ) -> None:
        """Гейт не декорация: явный запрет по-прежнему закрывает доступ.

        Это аварийный выключатель. Без проверки «ядро» однажды прочитали бы как
        «проверять нечего», и гейт тихо перестал бы работать.
        """

        from app.models.feature import Feature, FeatureEnablement

        headers = await make_auth_headers(RoleEnum.ADMIN)

        async with sessionmaker() as session:
            tenant_id = (
                await session.execute(select(Tenant.id).where(Tenant.slug == "test"))
            ).scalar_one()
            feature = (
                await session.execute(select(Feature).where(Feature.code == "imports"))
            ).scalar_one_or_none()
            if feature is None:
                feature = Feature(code="imports", title="Импорт данных")
                session.add(feature)
                await session.flush()
            row = (
                await session.execute(
                    select(FeatureEnablement).where(
                        FeatureEnablement.tenant_id == str(tenant_id),
                        FeatureEnablement.feature_id == feature.id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                # Обновить-или-вставить: вторая строка выдачи ломает
                # уникальность и делает ответ гейта неопределённым.
                session.add(
                    FeatureEnablement(
                        tenant_id=str(tenant_id), feature_id=feature.id, on=False
                    )
                )
            else:
                row.on = False
            await session.commit()

        response = await async_client.get(f"{API}/targets", headers=headers)

        assert response.status_code == 404, response.text
        assert response.json()["detail"]["code"] == "IMPORTS_DISABLED"


@pytest.mark.anyio
class TestTemplateAndDryRun:
    async def test_downloaded_template_is_accepted_by_autodetection(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)

        template = await async_client.get(f"{API}/targets/persons/template", headers=headers)
        assert template.status_code == 200, template.text

        header_line = template.text.strip().splitlines()[0].lstrip("﻿")
        body = (header_line + "\nАКМЕ,Иванов,Иван,001,05.03.1980\n").encode("utf-8")

        preview = await async_client.post(
            f"{API}/persons/dry-run", files=_upload(body), headers=headers
        )

        assert preview.status_code == 200, preview.text
        assert preview.json()["counts"]["create"] == 1

    async def test_dry_run_writes_nothing(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        before = await _count_persons(sessionmaker, imports_tenant)

        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,05.03.1980\n")),
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["counts"]["create"] == 1
        assert await _count_persons(sessionmaker, imports_tenant) == before

    async def test_missing_required_column_rejects_the_file_once(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        body = b"\xef\xbb\xbf" + "Организация,Имя\nАКМЕ,Иван\n".encode("utf-8")

        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(body),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["code"] == "IMPORT_REQUIRED_COLUMNS_MISSING"
        assert "Фамилия" in detail["missing_columns"]

    async def test_unknown_company_is_reported_as_a_grouped_summary(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/dry-run",
            files=_upload(_csv("НЕТ ТАКОЙ,Иванов,Иван,001,\n")),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["counts"]["error"] == 1
        assert body["unknown_references"]["company"] == ["НЕТ ТАКОЙ"]


@pytest.mark.anyio
class TestApply:
    async def test_partial_import_keeps_good_rows_and_parks_bad_ones(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = _csv(
            "АКМЕ,Иванов,Иван,001,05.03.1980\n",
            "АКМЕ,,Пётр,002,\n",  # нет фамилии — строка «на исправление»
        )

        response = await async_client.post(
            f"{API}/persons/apply", files=_upload(body), headers=headers
        )

        assert response.status_code == 201, response.text
        batch = response.json()["batch"]
        assert (batch["created_count"], batch["failed_count"]) == (1, 1)
        assert await _count_persons(sessionmaker, imports_tenant) == 1

        rows = await async_client.get(
            f"{API}/batches/{batch['id']}/rows?action=failed", headers=headers
        )
        assert rows.status_code == 200, rows.text
        assert rows.json()[0]["errors"][0]["code"] == "required"

    async def test_reimporting_the_same_file_creates_nothing(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        body = _csv("АКМЕ,Иванов,Иван,001,05.03.1980\n")

        first = await async_client.post(
            f"{API}/persons/apply", files=_upload(body), headers=headers
        )
        second = await async_client.post(
            f"{API}/persons/apply", files=_upload(body), headers=headers
        )

        assert first.json()["batch"]["created_count"] == 1
        assert second.json()["batch"]["created_count"] == 0
        assert second.json()["batch"]["skipped_count"] == 1
        assert await _count_persons(sessionmaker, imports_tenant) == 1

    async def test_changed_row_updates_the_existing_person(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,05.03.1980\n")),
            headers=headers,
        )

        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Пётр,001,05.03.1980\n")),
            headers=headers,
        )

        batch = response.json()["batch"]
        assert (batch["updated_count"], batch["created_count"]) == (1, 0)

    async def test_row_rejected_by_the_database_does_not_sink_the_file(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        """Ограничение БД, которого планировщик видеть не мог, валит ОДНУ строку.

        Мягко удалённая должность продолжает занимать UNIQUE(tenant, company, name),
        поэтому её повторный импорт отвергается базой. Без изоляции строки savepoint'ом
        это был бы 500 на весь файл — вместо «частичного импорта» из разд. 71.1.
        """

        from app.models.master_data import Company, Position

        headers = await make_auth_headers(RoleEnum.ADMIN)
        async with sessionmaker() as session:
            company = (
                await session.execute(select(Company).where(Company.tenant_id == imports_tenant))
            ).scalar_one()
            session.add(
                Position(
                    tenant_id=imports_tenant,
                    company_id=company.id,
                    name="Слесарь",
                    deleted_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        body = "Организация,Должность\nАКМЕ,Слесарь\nАКМЕ,Электрик\n".encode("utf-8")
        response = await async_client.post(
            f"{API}/positions/apply", files=_upload(body), headers=headers
        )

        assert response.status_code == 201, response.text
        batch = response.json()["batch"]
        # Хорошая строка прошла, плохая отложена — файл не упал целиком.
        assert (batch["created_count"], batch["failed_count"]) == (1, 1)

        rows = await async_client.get(
            f"{API}/batches/{batch['id']}/rows?action=failed", headers=headers
        )
        assert rows.json()[0]["errors"][0]["code"] == "constraint_violation"

    async def test_batch_keeps_the_mapping_for_a_repeat_run(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,\n")),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        mapping = response.json()["batch"]["mapping"]
        assert mapping["last_name"] == "Фамилия"
        assert mapping["personnel_number"] == "Табельный номер"


@pytest.mark.anyio
class TestRollback:
    async def test_rollback_removes_what_the_batch_created(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        applied = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,05.03.1980\n")),
            headers=headers,
        )
        batch_id = applied.json()["batch"]["id"]
        assert await _count_persons(sessionmaker, imports_tenant) == 1

        response = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "rolled_back"
        assert await _count_persons(sessionmaker, imports_tenant) == 0

    async def test_rollback_restores_overwritten_values(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant, sessionmaker
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,05.03.1980\n")),
            headers=headers,
        )
        overwrite = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Пётр,001,05.03.1980\n")),
            headers=headers,
        )
        batch_id = overwrite.json()["batch"]["id"]

        rollback = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)
        assert rollback.status_code == 200, rollback.text

        async with sessionmaker() as session:
            person = (
                await session.execute(select(Person).where(Person.tenant_id == imports_tenant))
            ).scalar_one()
        # Перезаписанное имя вернулось — снимок before_values не декоративный.
        assert person.first_name == "Иван"

    async def test_second_rollback_is_refused_rather_than_pretended(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        applied = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv("АКМЕ,Иванов,Иван,001,\n")),
            headers=headers,
        )
        batch_id = applied.json()["batch"]["id"]
        await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        again = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        assert again.status_code == 409, again.text
        assert again.json()["detail"]["code"] == "IMPORT_BATCH_ALREADY_ROLLED_BACK"

    async def test_unknown_batch_is_not_found(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.get(
            f"{API}/batches/00000000-0000-0000-0000-000000000000",
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 404, response.text
