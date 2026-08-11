"""OPS-72 срез-3 (разд. 72.3): исполнение удаления данных арендатора.

Срез-2 остановился на плане: удаление «в обратном порядке зависимостей» падает
на циклах внешних ключей. Здесь закрепляется то, что делает исполнение
безопасным:

* цикл разрывается ТОЛЬКО обнулением необязательных ссылок, и это видно в акте;
  цикл без единой такой ссылки — отказ, а не частичное удаление;
* **изоляция**: удаление одного арендатора не трогает данные другого — это и
  есть тот дефект, который на необратимой операции не переживёт ни один клиент;
* **grace защищает**: до истечения срока удаление отказывает;
* **акт переживает удаление** и повторный вызов возвращает его же (кнопку
  нажмут дважды — второй раз не должен выглядеть как «удалили ещё раз»);
* **срок хранения протекает вверх по ссылкам**: удерживается ``person`` —
  значит удерживается и его ``company``, иначе удаление оставит сироту;
* **список обезличиваемых колонок полон**: тест сам ищет идентификаторы в
  удерживаемых таблицах, потому что пропущенная колонка = ПДн, оставшиеся в
  базе, которую клиент считает вычищенной.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.modules.offboarding.lifecycle import OffboardingStateError
from app.modules.offboarding.purge import ANONYMIZED_COLUMNS, TenantPurgeService
from app.modules.offboarding.schema_graph import (
    ForeignLink,
    SchemaGraph,
    UnbreakableCycleError,
    reflect_schema_graph,
)
from app.modules.privacy.registry import PdnProcessingRegistryService
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


class _FakeStorage:
    """Хранилище-заглушка: помнит удалённое и умеет падать на одном ключе."""

    def __init__(self, *, failing: str | None = None) -> None:
        self.deleted: list[str] = []
        self.failing = failing

    def delete(self, key: str) -> None:
        if key == self.failing:
            raise RuntimeError("хранилище недоступно")
        self.deleted.append(key)


async def _purge_service(
    data_factory: TestDataFactory,
    session: AsyncSession,
    slug: str,
    *,
    storage: _FakeStorage | None = None,
):
    tenant = await data_factory.ensure_tenant(slug=slug, session=session)
    return tenant, TenantPurgeService(
        session,
        tenant_id=str(tenant.id),
        tenant_slug=tenant.slug,
        storage=storage or _FakeStorage(),
    )


async def _count(session: AsyncSession, table: str, tenant_id: str) -> int:
    return int(
        (
            await session.execute(
                text(f'SELECT count(*) FROM "{table}" WHERE tenant_id = :tenant'),
                {"tenant": tenant_id},
            )
        ).scalar_one()
    )


@pytest.mark.anyio
class TestPurgeExecution:
    async def test_purge_deletes_rows_and_leaves_an_act(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, service = await _purge_service(data_factory, test_db_session, "purge-a")
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        await data_factory.create_person(
            tenant=tenant, company=company, session=test_db_session
        )
        # grace_days=0 — законный «удалить сейчас»: срок задаётся заявкой, а не
        # флагом, обходящим проверку.
        await service.lifecycle.request(grace_days=0)
        await test_db_session.commit()

        act = await service.execute()
        await test_db_session.commit()

        assert act.rows_deleted >= 2, act.deleted_rows
        assert await _count(test_db_session, "person", str(tenant.id)) == 0
        assert await _count(test_db_session, "company", str(tenant.id)) == 0

        record = await service.lifecycle.current()
        assert record is not None
        assert record.status == "purged"
        assert record.purged_at is not None
        # Акт остаётся ровно там, где его будут искать — когда данных уже нет.
        assert record.purge_act["rows_deleted"] == act.rows_deleted
        assert await _count(test_db_session, "tenant_offboarding", str(tenant.id)) == 1

    async def test_purge_does_not_touch_another_tenant(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Изоляция на необратимой операции — единственная проверка, ошибка в
        которой не лечится ничем."""

        victim, service = await _purge_service(data_factory, test_db_session, "purge-b")
        neighbour = await data_factory.ensure_tenant(slug="purge-b-neighbour", session=test_db_session)
        await data_factory.create_person(
            tenant=victim, tenant_slug="purge-b", session=test_db_session
        )
        await data_factory.create_person(
            tenant=neighbour, tenant_slug="purge-b-neighbour", session=test_db_session
        )
        await service.lifecycle.request(grace_days=0)
        await test_db_session.commit()

        await service.execute()
        await test_db_session.commit()

        assert await _count(test_db_session, "person", str(victim.id)) == 0
        assert await _count(test_db_session, "person", str(neighbour.id)) == 1

    async def test_purge_refuses_while_grace_is_running(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        _, service = await _purge_service(data_factory, test_db_session, "purge-c")
        await service.lifecycle.request(grace_days=30)
        await test_db_session.commit()

        with pytest.raises(OffboardingStateError, match="Grace"):
            await service.execute()

    async def test_purge_refuses_without_a_request(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        _, service = await _purge_service(data_factory, test_db_session, "purge-d")

        with pytest.raises(OffboardingStateError):
            await service.execute()

    async def test_purge_is_idempotent(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Второй вызов возвращает ТОТ ЖЕ акт: повторное нажатие кнопки не
        должно выглядеть как второе, другое удаление."""

        tenant, service = await _purge_service(data_factory, test_db_session, "purge-e")
        await data_factory.create_person(
            tenant=tenant, tenant_slug="purge-e", session=test_db_session
        )
        await service.lifecycle.request(grace_days=0)
        await test_db_session.commit()

        first = await service.execute()
        await test_db_session.commit()
        second = await service.execute()

        assert second.executed_at == first.executed_at
        assert second.deleted_rows == first.deleted_rows

    async def test_retention_keeps_and_anonymizes_instead_of_deleting(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, service = await _purge_service(data_factory, test_db_session, "purge-f")
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            email="ivanov@example.com",
            phone="+70000000000",
            snils="123-456-789 00",
        )
        await PdnProcessingRegistryService(
            test_db_session, tenant_id=str(tenant.id)
        ).seed_defaults()
        await service.lifecycle.request(grace_days=0)
        await test_db_session.commit()

        act = await service.execute()
        await test_db_session.commit()

        assert act.anonymized_rows.get("person") == 1
        assert await _count(test_db_session, "person", str(tenant.id)) == 1
        # Родитель удерживаемой записи тоже уцелел — иначе остались бы сироты.
        assert await _count(test_db_session, "company", str(tenant.id)) == 1
        assert "company" in act.retained_tables

        row = (
            await test_db_session.execute(
                text(
                    "SELECT first_name, last_name, email, phone, snils, anonymized_at "
                    "FROM person WHERE tenant_id = :tenant"
                ),
                {"tenant": str(tenant.id)},
            )
        ).one()
        assert row[0] == "Обезличено"
        assert row[1].startswith("subject-")
        assert row[2] is None and row[3] is None and row[4] is None
        assert row[5] is not None

    async def test_files_are_deleted_by_keys_taken_from_rows(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Ключи собираются ДО удаления строк: после него узнать, что
        принадлежало арендатору, уже неоткуда."""

        storage = _FakeStorage(failing="tenants/purge-g/broken.pdf")
        tenant, service = await _purge_service(
            data_factory, test_db_session, "purge-g", storage=storage
        )
        _, version = await data_factory.create_document(
            tenant=tenant,
            session=test_db_session,
            version_file_key="tenants/purge-g/ok.pdf",
        )
        await test_db_session.execute(
            text(
                "UPDATE document SET storage_key = :key WHERE tenant_id = :tenant"
            ),
            {"key": "tenants/purge-g/broken.pdf", "tenant": str(tenant.id)},
        )
        await service.lifecycle.request(grace_days=0)
        await test_db_session.commit()

        act = await service.execute()
        await test_db_session.commit()

        assert "tenants/purge-g/ok.pdf" in storage.deleted
        assert act.files_deleted >= 1
        # Недоступный объект не отменяет удаление базы, но и не исчезает молча.
        assert act.files_failed == ["tenants/purge-g/broken.pdf"]
        assert version is not None


@pytest.mark.anyio
class TestPurgeEndpoint:
    async def test_purge_is_closed_for_admin(self, async_client, make_auth_headers) -> None:
        """Экспорт админу доверяем, уничтожение — нет."""

        response = await async_client.post(
            f"{API_PREFIX}/offboarding/purge",
            json={"confirm_slug": "test"},
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )
        assert response.status_code == 403, response.text

    async def test_wrong_confirmation_is_rejected(self, async_client, make_auth_headers) -> None:
        response = await async_client.post(
            f"{API_PREFIX}/offboarding/purge",
            json={"confirm_slug": "не-тот-арендатор"},
            headers=await make_auth_headers(RoleEnum.OWNER),
        )
        assert response.status_code == 400, response.text

    async def test_purge_without_request_is_conflict(
        self, async_client, make_auth_headers
    ) -> None:
        response = await async_client.post(
            f"{API_PREFIX}/offboarding/purge",
            json={"confirm_slug": "test"},
            headers=await make_auth_headers(RoleEnum.OWNER),
        )
        assert response.status_code == 409, response.text


class TestSchemaGraph:
    def test_cycle_is_broken_by_a_nullable_link(self) -> None:
        graph = SchemaGraph(
            tables=("a", "b"),
            links=(
                ForeignLink(child="a", parent="b", columns=("b_id",), nullable=True),
                ForeignLink(child="b", parent="a", columns=("a_id",), nullable=False),
            ),
        )

        order, broken = graph.deletion_order(["a", "b"])

        assert [link.child for link in broken] == ["a"]
        # Обязательная ссылка уцелела: b по-прежнему удаляется раньше a.
        assert order.index("b") < order.index("a")

    def test_cycle_without_nullable_links_is_refused(self) -> None:
        graph = SchemaGraph(
            tables=("a", "b"),
            links=(
                ForeignLink(child="a", parent="b", columns=("b_id",), nullable=False),
                ForeignLink(child="b", parent="a", columns=("a_id",), nullable=False),
            ),
        )

        with pytest.raises(UnbreakableCycleError):
            graph.deletion_order(["a", "b"])

    def test_retention_leaks_upwards(self) -> None:
        graph = SchemaGraph(
            tables=("child", "parent", "grandparent", "unrelated"),
            links=(
                ForeignLink(child="child", parent="parent", columns=("p",), nullable=True),
                ForeignLink(
                    child="parent", parent="grandparent", columns=("g",), nullable=False
                ),
            ),
        )

        promoted = graph.retention_closure(["child"])

        assert set(promoted) == {"parent", "grandparent"}
        assert "unrelated" not in promoted


@pytest.mark.anyio
class TestAnonymizationCoverage:
    async def test_person_columns_match_pdn_erasure(self) -> None:
        """Два разных обезличивания одного человека — источник расхождений."""

        from app.modules.privacy.consents import SCRUBBED_PERSON_FIELDS

        covered = set(ANONYMIZED_COLUMNS["person"]) - {"anonymized_at", "position_title"}
        assert covered == set(SCRUBBED_PERSON_FIELDS)

    async def test_every_identifier_in_retained_tables_is_scrubbed(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Тест сам ищет идентификаторы: новая колонка с ПДн в удерживаемой
        таблице обязана либо попасть в список, либо уронить CI."""

        from app.modules.offboarding.lifecycle import ACTIVITY_TABLES

        identifiers = (
            "first_name",
            "last_name",
            "middle_name",
            "birth_date",
            "email",
            "phone",
            "personnel_number",
            "snils",
            "passport",
            "fio",
        )
        tenant = await data_factory.ensure_tenant(slug="purge-scan", session=test_db_session)
        assert tenant is not None
        retained = {table for tables in ACTIVITY_TABLES.values() for table in tables}
        graph = await reflect_schema_graph(test_db_session, retained)

        connection = await test_db_session.connection()

        def _columns(sync_conn):  # noqa: ANN001, ANN202 - sync bridge
            from sqlalchemy import inspect as sa_inspect

            inspector = sa_inspect(sync_conn)
            return {
                table: [column["name"] for column in inspector.get_columns(table)]
                for table in graph.tables
            }

        by_table = await connection.run_sync(_columns)
        for table, columns in by_table.items():
            for column in columns:
                if not any(marker in column for marker in identifiers):
                    continue
                assert column in ANONYMIZED_COLUMNS.get(table, {}), (
                    f"{table}.{column} выглядит идентификатором, но не обезличивается"
                )


# Порядок удаления на ЖИВОЙ схеме PostgreSQL (там, где циклы и есть) проверяет
# db-маркированный `backend/tests/test_offboarding_purge_order_pg.py`: SQLite
# внешние ключи по умолчанию не проверяет, поэтому «работает на SQLite» ничего
# не говорит о безопасности порядка.
