"""OPS-71 срез-2 (разд. 71.1, строка «Прогресс»): асинхронный импорт.

Что закрепляется:

* синхронная ручка отвергает файл сверх своего потолка И называет асинхронную
  как выход — отказ без подсказки заставляет резать файл вручную;
* постановка отвечает 202 и заводит партию в `pending`, файл лежит в хранилище
  ДО постановки задачи (обратный порядок = гонка «воркер быстрее файла»);
* прогресс виден ПО ХОДУ работы, а не только в конце: `processed_rows` растёт
  и коммитится порциями;
* обрыв даёт `failed` С ПРИЧИНОЙ, а применённые до обрыва строки остаются в
  отчёте и снимаются штатным откатом партии;
* повторный запуск той же задачи (ретрай брокера) НЕ применяет партию дважды;
* исходник удаляется по достижении терминального статуса — это ПДн (SEC-66).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.imports import ImportBatch
from app.models.master_data import Person
from app.models.models import RoleEnum
from app.modules.imports import runner
from app.modules.imports.parsers import MAX_IMPORT_ROWS
from app.modules.imports.registry import PERSONS_TARGET
from app.modules.imports.runner import execute_import_batch

API = "/api/v1/imports"
HEADER_LINE = "Организация,Фамилия,Имя,Табельный номер\n"


def _csv(rows: int, *, start: int = 1) -> bytes:
    body = "".join(f"АКМЕ,Иванов{i},Иван,{i:05d}\n" for i in range(start, start + rows))
    return (HEADER_LINE + body).encode("utf-8")


def _upload(content: bytes, name: str = "staff.csv") -> dict:
    return {"file": (name, content, "text/csv")}


@pytest.fixture()
async def imports_tenant(sessionmaker, data_factory):
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "imports"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="imports", title="Импорт данных")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=True))
        await session.commit()
        return tenant


@pytest.fixture()
def fake_storage(monkeypatch: pytest.MonkeyPatch):
    """Хранилище в памяти: срез проверяет оркестрацию, а не S3."""

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
    """Брокера в тестах нет: запоминаем постановку и зовём раннер вручную."""

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


@pytest.mark.anyio
class TestSyncCeilingPointsToAsync:
    async def test_oversized_file_names_the_async_route(
        self, async_client: AsyncClient, make_auth_headers, imports_tenant
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/apply",
            files=_upload(_csv(MAX_IMPORT_ROWS + 1)),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 422, response.status_code
        detail = response.json()["detail"]
        assert detail["code"] == "IMPORT_FILE_TOO_MANY_ROWS"
        assert "asynchronous" in detail["message"].lower()


@pytest.mark.anyio
class TestEnqueue:
    async def test_accepts_and_returns_a_pending_batch(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
    ) -> None:
        response = await async_client.post(
            f"{API}/persons/apply-async",
            files=_upload(_csv(3)),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "pending"
        assert body["processed_rows"] == 0
        # Файл лежит в хранилище ДО постановки задачи, иначе воркер обгонит файл.
        assert len(fake_storage) == 1
        assert captured_jobs == [("test", body["id"])]

    async def test_enqueue_writes_nothing_to_the_target_table(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        await async_client.post(
            f"{API}/persons/apply-async",
            files=_upload(_csv(3)),
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )

        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 0


@pytest.mark.anyio
class TestExecution:
    async def _enqueue(self, async_client, headers, rows: int = 5) -> str:
        response = await async_client.post(
            f"{API}/persons/apply-async", files=_upload(_csv(rows)), headers=headers
        )
        assert response.status_code == 202, response.text
        return response.json()["id"]

    async def test_batch_runs_to_applied_and_creates_rows(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=5)

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch, chunk_size=2)

        status_response = await async_client.get(f"{API}/batches/{batch_id}", headers=headers)
        body = status_response.json()
        assert body["status"] == "applied"
        assert (body["processed_rows"], body["created_count"]) == (5, 5)
        assert body["finished_at"]
        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 5

    async def test_progress_is_visible_while_the_batch_is_running(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        """Прогресс, видимый только в конце, — это не прогресс."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=6)

        seen: list[tuple[str, int]] = []

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            original_commit = session.commit

            async def _spy_commit():
                await original_commit()
                # Читаем ИЗ ДРУГОЙ сессии: незакоммиченное состояние ей не видно,
                # поэтому рост здесь доказывает, что прогресс реально зафиксирован.
                async with sessionmaker() as observer:
                    row = await observer.get(ImportBatch, batch_id)
                    if row is not None:
                        seen.append((row.status, row.processed_rows))

            session.commit = _spy_commit  # type: ignore[method-assign]
            await execute_import_batch(session, imports_tenant, batch, chunk_size=2)

        running = [processed for status, processed in seen if status == "running"]
        assert running, seen
        # Значение РОСЛО порциями, а не прыгнуло из нуля в итог: между началом и
        # концом наблюдались промежуточные значения, видимые чужой сессией.
        intermediate = [p for p in running if 0 < p < 6]
        assert intermediate, seen
        assert running == sorted(running), seen

    async def test_rerun_of_the_same_batch_does_not_double_apply(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=3)

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)
        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 3

    async def test_source_file_is_removed_once_terminal(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=2)
        assert len(fake_storage) == 1

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        assert fake_storage == {}

    async def test_missing_source_fails_with_a_reason(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
    ) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=2)
        fake_storage.clear()  # исходник потерялся

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch)

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert body["status"] == "failed"
        # «failed» без причины отправляет человека читать логи воркера.
        assert "import_source_unavailable" in body["error_message"]

    async def test_partially_applied_failure_is_still_rollbackable(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        imports_tenant,
        fake_storage,
        captured_jobs,
        sessionmaker,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Порционный коммит — цена прогресса; отчёт обязан покрывать эту цену."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        batch_id = await self._enqueue(async_client, headers, rows=6)

        from app.modules.imports.service import ImportService

        original = ImportService._apply_row
        state = {"calls": 0}

        async def _explode(self, target, batch, planned, table):
            state["calls"] += 1
            if state["calls"] > 4:
                raise RuntimeError("worker died mid-file")
            return await original(self, target, batch, planned, table)

        monkeypatch.setattr(ImportService, "_apply_row", _explode)

        async with sessionmaker() as session:
            batch = await session.get(ImportBatch, batch_id)
            await execute_import_batch(session, imports_tenant, batch, chunk_size=2)

        body = (await async_client.get(f"{API}/batches/{batch_id}", headers=headers)).json()
        assert body["status"] == "failed"
        assert "worker died mid-file" in body["error_message"]

        applied = await _count_persons(sessionmaker, str(imports_tenant.id))
        assert applied > 0, "порции до обрыва должны были остаться"

        rollback = await async_client.post(f"{API}/batches/{batch_id}/rollback", headers=headers)
        assert rollback.status_code == 200, rollback.text
        assert await _count_persons(sessionmaker, str(imports_tenant.id)) == 0


def test_async_ceiling_is_higher_than_the_sync_one() -> None:
    from app.modules.imports.parsers import MAX_ASYNC_IMPORT_ROWS

    assert MAX_ASYNC_IMPORT_ROWS > MAX_IMPORT_ROWS


def test_source_key_stays_inside_the_tenant_prefix() -> None:
    from app.modules.files.storage import assert_tenant_key

    key = runner.build_source_key(tenant_id="t-1", batch_id="b-1", filename="../../etc/passwd")

    assert_tenant_key(tenant_id="t-1", key=key)
    assert PERSONS_TARGET.code  # реестр цел — ключ строится не из имени цели
