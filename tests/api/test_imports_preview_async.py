"""OPS-71 срез-5 (разд. 71.1, строка «Dry-run»): сухой прогон больших файлов в фоне.

Синхронный `dry-run` ограничен потолком строк, поэтому у файла сверх него
предпросмотра не было ВООБЩЕ — оставалось «применить и посмотреть, что вышло».
Здесь тот же план считается фоном.

Что закрепляется:

* предпросмотр НЕ ПИШЕТ в целевые таблицы — это и есть требование ТЗ;
* итог живёт в партии: счётчики «сколько было бы» и список строк на исправление;
* статус отдельный (`previewed`), а не `applied`: «применена» у партии, которая
  ничего не применяла, — ложь в интерфейсе и в отчётах;
* **откат предпросмотра отвергается**, а не отвечает «откачено»: иначе человек
  решит, что что-то отменил, и не станет искать настоящую партию;
* усечение длинного списка ошибок ВИДНО в отчёте, молча оно не происходит.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.imports import ImportBatch
from app.models.master_data import Person
from app.models.models import RoleEnum
from app.modules.imports import runner
from app.modules.imports.runner import execute_import_batch

API = "/api/v1/imports"
HEADER = "Организация,Фамилия,Имя,Табельный номер\n"


def _csv(rows: list[str]) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def _good(n: int) -> list[str]:
    return [f"АКМЕ,Иванов{i},Иван,{i:05d}\n" for i in range(1, n + 1)]


def _broken(n: int) -> list[str]:
    # Пустая фамилия — обязательное поле, строка уходит «на исправление».
    return [f"АКМЕ,,Иван,{i:05d}\n" for i in range(1000, 1000 + n)]


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        await session.commit()
        return tenant


@pytest.fixture()
def fake_storage(monkeypatch: pytest.MonkeyPatch):
    store: dict[str, bytes] = {}

    def _store(*, key: str, content: bytes, filename: str) -> None:
        store[key] = content

    def _load(key: str) -> bytes:
        if key not in store:
            raise FileNotFoundError(key)
        return store[key]

    def _discard(key: str | None) -> None:
        if key:
            store.pop(key, None)

    import app.modules.imports.api as imports_api

    monkeypatch.setattr(runner, "store_source", _store)
    monkeypatch.setattr(runner, "load_source", _load)
    monkeypatch.setattr(runner, "discard_source", _discard)
    monkeypatch.setattr(imports_api, "store_source", _store)
    monkeypatch.setattr(imports_api, "discard_source", _discard)
    return store


@pytest.fixture()
def captured_jobs(monkeypatch: pytest.MonkeyPatch):
    import app.modules.imports.api as imports_api

    calls: list[tuple[str, str]] = []

    class _Task:
        @staticmethod
        def delay(tenant_slug: str, batch_id: str):
            calls.append((tenant_slug, batch_id))

    monkeypatch.setattr(imports_api, "run_import_batch_job", _Task)
    return calls


async def _count_persons(sessionmaker, tenant_id: str) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None))
            )
        ).scalar_one()


async def _enqueue_preview(async_client, headers, body: bytes) -> str:
    response = await async_client.post(
        f"{API}/persons/dry-run-async", files=_upload(body), headers=headers
    )
    assert response.status_code == 202, response.text
    payload = response.json()
    assert payload["mode"] == "preview"
    assert payload["status"] == "pending"
    return payload["id"]


@pytest.mark.anyio
class TestAsyncPreview:
    async def test_preview_writes_nothing_but_reports_the_plan(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(async_client, headers, _csv(_good(3) + _broken(2)))

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert body["status"] == "previewed"
        assert body["mode"] == "preview"
        # «Сколько БЫЛО БЫ создано» и «сколько отвергнуто» — это и есть предпросмотр.
        assert (body["created_count"], body["failed_count"], body["total_rows"]) == (3, 2, 5)
        # Главное требование ТЗ: без записи в БД.
        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 0

    async def test_rows_to_fix_are_available_with_line_numbers(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(async_client, headers, _csv(_good(1) + _broken(2)))

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        rows = (
            await async_client.get(f"{API}/batches/{batch_id}/rows?action=failed", headers=headers)
        ).json()
        assert len(rows) == 2
        assert rows[0]["errors"][0]["code"] == "required"
        assert rows[0]["row_number"] > 1

    async def test_long_error_list_is_truncated_visibly(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """«Показано 3» без пометки читается как «ошибок ровно 3»."""

        monkeypatch.setattr(runner, "MAX_PREVIEW_ERROR_ROWS", 3)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(async_client, headers, _csv(_broken(7)))

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert body["failed_count"] == 7
        assert body["notes"]["errors_total"] == 7
        assert body["notes"]["errors_truncated"] is True

        rows = (
            await async_client.get(f"{API}/batches/{batch_id}/rows?action=failed", headers=headers)
        ).json()
        assert len(rows) == 3

    async def test_unknown_reference_is_reported_in_the_batch(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(
            async_client, headers, _csv(["НЕТ ТАКОЙ,Иванов,Иван,00001\n"])
        )

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert body["notes"]["unknown_references"]["company"] == ["НЕТ ТАКОЙ"]

    async def test_rollback_of_a_preview_is_refused(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(async_client, headers, _csv(_good(2)))

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        response = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)

        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "IMPORT_BATCH_IS_PREVIEW"

    async def test_source_file_is_discarded_after_preview(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await _enqueue_preview(async_client, headers, _csv(_good(1)))
        assert len(fake_storage) == 1

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        assert fake_storage == {}

    async def test_apply_batches_stay_in_apply_mode(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
    ) -> None:
        """Режим не должен «протечь»: обычная фоновая загрузка остаётся применяющей."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.post(
            f"{API}/persons/apply-async", files=_upload(_csv(_good(1))), headers=headers
        )

        assert response.json()["mode"] == "apply"

    async def test_sync_apply_batch_is_apply_mode_too(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.post(
            f"{API}/persons/apply", files=_upload(_csv(_good(1))), headers=headers
        )

        assert response.status_code == 201, response.text
        assert response.json()["batch"]["mode"] == "apply"
