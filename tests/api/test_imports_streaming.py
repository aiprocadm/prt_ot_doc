"""OPS-71 срез-10 (разд. 71.1): потоковая обработка файла порциями.

Раньше фоновый путь держал ВЕСЬ файл в памяти — это и было единственной причиной
потолка 100 000 строк. Теперь файл читается лениво и обрабатывается порциями.

Что закрепляется — ровно то, что порционная обработка ломает первой:

* **номера строк сквозные**: ошибка в третьей порции обязана указывать на свой
  номер в ФАЙЛЕ, иначе человек ищет её не там;
* **дубль виден через границу порции**: оригинал в первой, копия во второй —
  повторный импорт иначе создал бы вторую запись;
* сводка неизвестных значений справочников собирается по ВСЕМУ файлу, а не по
  последней порции;
* файл сверх синхронного потолка проходит фоновым путём.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.imports import ImportBatch
from app.models.master_data import Person
from app.models.models import RoleEnum
from app.modules.imports import runner
from app.modules.imports.parsers import MAX_IMPORT_ROWS, open_import_source
from app.modules.imports.runner import execute_import_batch

API = "/api/v1/imports"
HEADER = "Организация,Фамилия,Имя,Табельный номер\n"


def _csv(rows: list[str]) -> bytes:
    return (HEADER + "".join(rows)).encode("utf-8")


def _person(i: int, number: int | None = None) -> str:
    return f"АКМЕ,Иванов{i},Иван,{number if number is not None else i:05d}\n"


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
    import app.modules.imports.api as imports_api

    monkeypatch.setattr(
        runner, "store_source", lambda *, key, content, filename: store.__setitem__(key, content)
    )
    monkeypatch.setattr(runner, "load_source", lambda key: store[key])
    monkeypatch.setattr(runner, "discard_source", lambda key: store.pop(key, None))
    monkeypatch.setattr(
        imports_api,
        "store_source",
        lambda *, key, content, filename: store.__setitem__(key, content),
    )
    monkeypatch.setattr(imports_api, "discard_source", lambda key: store.pop(key, None))
    return store


@pytest.fixture()
def captured_jobs(monkeypatch: pytest.MonkeyPatch):
    import app.modules.imports.api as imports_api

    class _Task:
        @staticmethod
        def delay(*args):
            return None

    monkeypatch.setattr(imports_api, "run_import_batch_job", _Task)
    return _Task


async def _count_persons(sessionmaker, tenant_id: str) -> int:
    async with sessionmaker() as session:
        return (
            await session.execute(
                select(func.count())
                .select_from(Person)
                .where(Person.tenant_id == tenant_id, Person.deleted_at.is_(None))
            )
        ).scalar_one()


class TestLazySource:
    def test_rows_are_not_materialised(self) -> None:
        """Поток обязан быть ленивым — иначе весь смысл среза теряется."""

        body = _csv([_person(i) for i in range(1, 6)])

        headers, rows = open_import_source("staff.csv", body)

        assert headers[0] == "Организация"
        assert not isinstance(rows, list)
        assert len(list(rows)) == 5

    def test_xlsx_streams_too(self) -> None:
        import io

        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Организация", "Фамилия"])
        sheet.append(["АКМЕ", "Иванов"])
        buffer = io.BytesIO()
        workbook.save(buffer)

        headers, rows = open_import_source("staff.xlsx", buffer.getvalue())

        assert headers == ["Организация", "Фамилия"]
        assert [r["Фамилия"] for r in rows] == ["Иванов"]


@pytest.mark.anyio
class TestChunkBoundaries:
    async def _run(self, async_client, headers, sessionmaker, tenant, body: bytes, chunk: int):
        enqueued = await async_client.post(
            f"{API}/persons/apply-async", files=_upload(body), headers=headers
        )
        assert enqueued.status_code == 202, enqueued.text
        batch_id = enqueued.json()["id"]
        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, tenant, batch, chunk_size=chunk)
        return batch_id

    async def test_row_numbers_stay_true_to_the_file(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        """Ошибка в третьей порции должна указывать на свой номер в файле."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        rows = [_person(i) for i in range(1, 7)]
        rows.append("АКМЕ,,Пётр,00099\n")  # строка 8 файла: нет фамилии
        batch_id = await self._run(
            async_client, headers, sessionmaker, imports_tenant, _csv(rows), chunk=2
        )

        failed = (
            await async_client.get(f"{API}/batches/{batch_id}/rows?action=failed", headers=headers)
        ).json()

        assert [r["row_number"] for r in failed] == [8]

    async def test_duplicate_is_caught_across_the_chunk_boundary(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        """Оригинал в первой порции, копия во второй — иначе появится дубль."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        rows = [_person(1, 111), _person(2, 222), _person(3, 111)]
        batch_id = await self._run(
            async_client, headers, sessionmaker, imports_tenant, _csv(rows), chunk=2
        )

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert (body["created_count"], body["failed_count"]) == (2, 1)
        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 2

        failed = (
            await async_client.get(f"{API}/batches/{batch_id}/rows?action=failed", headers=headers)
        ).json()
        assert failed[0]["errors"][0]["code"] == "duplicate_in_file"

    async def test_unknown_references_are_collected_over_the_whole_file(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        rows = [
            "ПЕРВАЯ,Иванов,Иван,00001\n",
            _person(2),
            "ВТОРАЯ,Петров,Пётр,00003\n",
        ]
        batch_id = await self._run(
            async_client, headers, sessionmaker, imports_tenant, _csv(rows), chunk=1
        )

        notes = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()[
            "notes"
        ]
        assert sorted(notes["unknown_references"]["company"]) == ["ВТОРАЯ", "ПЕРВАЯ"]

    async def test_file_over_the_sync_ceiling_goes_through(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        """Ровно тот файл, который синхронная ручка отвергает."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        rows = [_person(i) for i in range(1, MAX_IMPORT_ROWS + 2)]
        body = _csv(rows)

        rejected = await async_client.post(
            f"{API}/persons/apply", files=_upload(body), headers=headers
        )
        assert rejected.status_code == 422

        batch_id = await self._run(
            async_client, headers, sessionmaker, imports_tenant, body, chunk=1000
        )

        result = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert result["status"] == "applied"
        assert result["created_count"] == MAX_IMPORT_ROWS + 1
