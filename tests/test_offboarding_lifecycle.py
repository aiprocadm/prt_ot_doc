"""OPS-72 срез-2 (разд. 72.3): офбординг — grace-период и план удаления.

ТЗ: «После ухода — управляемое удаление, а не "данные висят вечно" или "удалили
сразу и потеряли"».

Что здесь закрепляется:

* **grace-период** живёт на записи, а не в голове поддержки; повторная заявка не
  обнуляет срок — клиент, нажавший кнопку дважды, не должен терять дни;
* **отмена не удаляет запись**: история расторжений — часть ответа на вопрос
  «что происходило с нашими данными»;
* **юридические исключения берутся из реестра обработки** (SEC-66 срез-3), а не
  из отдельного справочника: у процесса указан срок хранения вместе со ссылкой на
  норму, поэтому «почему это нельзя удалить» — данные, а не мнение;
* таблица под действующим сроком планируется к **обезличиванию**, а не к
  удалению — ровно то, чего требует разд. 72.3.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incidents import (
    Incident,
    IncidentPerson,
    IncidentPersonRole,
    IncidentStage,
    IncidentStatus,
    IncidentType,
)
from app.models.models import RoleEnum
from app.modules.offboarding.lifecycle import (
    ACTIVITY_TABLES,
    DEFAULT_GRACE_DAYS,
    TenantOffboardingService,
)
from app.modules.privacy.registry import PdnProcessingRegistryService
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


async def _service(data_factory: TestDataFactory, session: AsyncSession, slug: str):
    tenant = await data_factory.ensure_tenant(slug=slug, session=session)
    return tenant, TenantOffboardingService(
        session, tenant_id=str(tenant.id), tenant_slug=tenant.slug
    )


@pytest.mark.anyio
class TestOffboardingLifecycle:
    async def test_request_starts_the_grace_period(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        _, service = await _service(data_factory, test_db_session, "offb-a")

        record = await service.request(reason="переезд", grace_days=14)

        assert record.status == "grace"
        assert record.grace_days == 14
        assert record.grace_until - record.requested_at == timedelta(days=14)

    async def test_repeated_request_does_not_reset_the_clock(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Клиент, нажавший кнопку дважды, не должен терять дни grace-периода."""

        _, service = await _service(data_factory, test_db_session, "offb-b")

        first = await service.request(grace_days=30)
        second = await service.request(grace_days=5)

        assert second.id == first.id
        assert second.grace_days == 30

    async def test_cancel_keeps_the_record(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        _, service = await _service(data_factory, test_db_session, "offb-c")
        await service.request(reason="ушли")

        cancelled = await service.cancel(reason="вернулись")

        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_at is not None
        # История расторжений остаётся: её спросят при разборе «что было с данными».
        assert await service.current() is not None

    async def test_cancel_without_active_request_returns_none(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        _, service = await _service(data_factory, test_db_session, "offb-d")
        assert await service.cancel() is None

    async def test_default_grace_is_configurable_not_hardcoded_in_handlers(self) -> None:
        assert DEFAULT_GRACE_DAYS > 0


@pytest.mark.anyio
class TestPurgePlan:
    async def test_retention_from_the_processing_registry_protects_data(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Ключевая связка: срок хранения из реестра обработки → обезличивание."""

        tenant, service = await _service(data_factory, test_db_session, "offb-e")
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        await data_factory.create_person(tenant=tenant, company=company, session=test_db_session)
        # Реестр обработки задаёт срок хранения ВМЕСТЕ со ссылкой на норму.
        await PdnProcessingRegistryService(
            test_db_session, tenant_id=str(tenant.id)
        ).seed_defaults()
        await service.request()
        await test_db_session.commit()

        plan = await service.build_purge_plan()

        by_table = {item.table: item for item in plan.tables}
        assert "person" in by_table, "у арендатора есть сотрудники — таблица должна быть в плане"
        person_plan = by_table["person"]
        assert person_plan.action == "anonymize"
        # Обоснование — не «потому что», а конкретная норма из реестра.
        assert "ФЗ-125" in person_plan.reason or "мес." in person_plan.reason
        assert plan.rows_to_anonymize >= 1

    async def test_tables_without_retention_are_planned_for_deletion(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, service = await _service(data_factory, test_db_session, "offb-f")
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        await data_factory.create_person(tenant=tenant, company=company, session=test_db_session)
        await service.request()
        await test_db_session.commit()

        # Реестр обработки НЕ заполнен → действующих сроков нет.
        plan = await service.build_purge_plan()

        assert plan.tables, "план не должен быть пустым при наличии данных"
        assert all(item.action == "delete" for item in plan.tables)
        assert plan.rows_to_anonymize == 0

    async def test_plan_reports_whether_grace_has_expired(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Удалять до истечения grace нельзя — план обязан это показывать."""

        _, service = await _service(data_factory, test_db_session, "offb-g")
        await service.request(grace_days=30)
        await test_db_session.commit()

        plan = await service.build_purge_plan()
        assert plan.grace_expired is False

    async def test_материалы_расследования_не_удаляются(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Срез-224. Реестр обработки даёт процессу «Расследование несчастных
        случаев» срок 45 лет со ссылкой на ст. 230.1 ТК РФ. Значит участники
        происшествия и журнал расследования обязаны попасть в «обезличить», а не
        в «удалить».

        До среза-224 карта процессов называла ``incident_persons`` и
        ``incident_investigations`` — таблицы, которых у моделей нет (остались от
        прежних волн, миграции их создают пустыми). Настоящие ``incident_person``
        и ``incident_log`` не были названы нигде, и план 45-летние материалы
        УДАЛЯЛ.
        """

        tenant, service = await _service(data_factory, test_db_session, "offb-i")
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=test_db_session
        )
        person = await data_factory.create_person(
            tenant=tenant, company=company, session=test_db_session
        )
        incident = Incident(
            tenant_id=str(tenant.id),
            title="Падение с высоты",
            incident_type=IncidentType.ACCIDENT,
            company_id=str(company.id),
            site_id=str(site.id),
            status=IncidentStatus.REPORTED,
            investigation_stage=IncidentStage.INVESTIGATION,
        )
        test_db_session.add(incident)
        await test_db_session.flush()
        test_db_session.add(
            IncidentPerson(
                tenant_id=str(tenant.id),
                incident_id=str(incident.id),
                person_id=str(person.id),
                role=IncidentPersonRole.VICTIM,
            )
        )
        await PdnProcessingRegistryService(
            test_db_session, tenant_id=str(tenant.id)
        ).seed_defaults()
        await service.request()
        await test_db_session.commit()

        plan = await service.build_purge_plan()

        by_table = {item.table: item for item in plan.tables}
        assert (
            "incident_person" in by_table
        ), "участники происшествия есть в базе — таблица обязана быть в плане"
        participants = by_table["incident_person"]
        assert participants.action == "anonymize", (
            f"материалы расследования планируются к «{participants.action}»: "
            f"{participants.reason}"
        )
        assert "230.1" in participants.reason or "мес." in participants.reason

    async def test_activity_table_map_references_real_tables(self) -> None:
        """Карта «процесс → таблицы» обязана ссылаться на ЖИВЫЕ таблицы — те, у
        которых есть модель.

        СТОРОЖ СМОТРЕЛ НЕ ТУДА (срез-224). Прежняя проверка спрашивала
        ``table in RLS_ENABLED_TABLES`` — а в этом списке НАРОЧНО лежат и
        таблицы-дубликаты без моделей: их армируют политиками, чтобы данные не
        утекли между арендаторами, пока владелец не решит их снести
        (``docs/security/RLS_RUNTIME_ROLE.md``). Поэтому опечатка во множественном
        числе (``incident_persons`` вместо ``incident_person``) проверку
        проходила, а срок хранения молча никого не защищал — ровно то, от чего
        проверка была написана.

        Теперь сторож требует МОДЕЛЬ: у мёртвого дубликата её нет.
        """

        import app.db.base  # noqa: F401 — подтягивает все модели
        from app.core.rls_policy import RLS_ENABLED_TABLES
        from app.db.session import SharedBase, TenantBase

        model_tables = set(SharedBase.metadata.tables) | set(TenantBase.metadata.tables)
        for code, tables in ACTIVITY_TABLES.items():
            for table in tables:
                assert table in model_tables, (
                    f"{code}: таблица «{table}» не имеет модели — это мёртвый дубликат "
                    f"прежних волн, и срок хранения на него не подействует"
                )
                assert table in RLS_ENABLED_TABLES, f"{code}: неизвестная таблица {table}"


@pytest.mark.anyio
class TestOffboardingEndpoints:
    async def test_request_status_cancel_roundtrip(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        base = f"{API_PREFIX}/offboarding"

        created = await async_client.post(
            f"{base}/request", json={"reason": "переезд", "grace_days": 7}, headers=headers
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "grace"

        current = await async_client.get(f"{base}/status", headers=headers)
        assert current.status_code == 200, current.text
        assert current.json()["offboarding"]["grace_days"] == 7

        cancelled = await async_client.post(
            f"{base}/cancel", json={"reason": "остаёмся"}, headers=headers
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"

    async def test_cancel_without_request_is_404(self, async_client, make_auth_headers) -> None:
        response = await async_client.post(
            f"{API_PREFIX}/offboarding/cancel",
            json={},
            headers=await make_auth_headers(RoleEnum.ADMIN),
        )
        assert response.status_code == 404, response.text

    async def test_purge_plan_endpoint_is_closed_for_line_manager(
        self, async_client, make_auth_headers
    ) -> None:
        response = await async_client.get(
            f"{API_PREFIX}/offboarding/purge-plan",
            headers=await make_auth_headers(RoleEnum.LINE_MANAGER),
        )
        assert response.status_code == 403, response.text
