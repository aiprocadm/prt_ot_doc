"""SEC-66 срез-3 (разд. 66.1 и 66.3): реестр обработки ПДн и договоры поручения.

Что здесь закрепляется:

* типовой реестр досевается и **не затирает** уже поправленные арендатором строки —
  иначе повторный засев уничтожал бы настройку сроков и получателей;
* процессы не удаляются, а прекращаются: реестр обязан показывать и прекращённую
  обработку;
* спец. категории (данные о здоровье) видны отдельным признаком — разд. 66.1
  требует отделять их от обычных;
* договоры поручения дают ответ «кто за что отвечает»: активный процесс, не
  покрытый ни одним действующим договором, попадает в `uncovered_activity_codes`.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.modules.privacy.registry import (
    DEFAULT_ACTIVITIES,
    InvalidRegistryValueError,
    PdnAgreementService,
    PdnProcessingRegistryService,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _headers(base: dict[str, str]) -> dict[str, str]:
    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


@pytest.mark.anyio
class TestProcessingRegistry:
    async def test_seed_defaults_is_idempotent_and_non_destructive(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))

        created = await service.seed_defaults()
        assert len(created) == len(DEFAULT_ACTIVITIES)

        # Арендатор поправил срок под себя...
        await service.upsert(
            code="training",
            name="Обучение (свой процесс)",
            purpose="training",
            legal_basis="legal_obligation",
            data_categories=["regular"],
            subject_categories=["employees"],
            retention_months=36,
            retention_basis="внутренний регламент",
        )
        # ...повторный засев не должен это затирать.
        again = await service.seed_defaults()
        assert again == []

        training = await service.get_by_code("training")
        assert training is not None
        assert training.retention_months == 36
        assert training.name == "Обучение (свой процесс)"

    async def test_default_registry_marks_health_as_special_category(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Разд. 66.1: медосмотры — специальная категория, это должно быть видно."""

        tenant = await data_factory.ensure_tenant(slug="pdn-reg-a", session=test_db_session)
        service = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))
        await service.seed_defaults()

        medical = await service.get_by_code("medical_exams")
        assert medical is not None
        assert "special_health" in medical.data_categories
        # Основание — обязанность работодателя, а не согласие: отзыв согласия не
        # прекращает обработку медданных.
        assert medical.legal_basis == "legal_obligation"
        assert medical.retention_basis, "срок без ссылки на норму в реестре бесполезен"

    async def test_deactivate_keeps_the_row(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="pdn-reg-b", session=test_db_session)
        service = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))
        await service.seed_defaults()

        deactivated = await service.deactivate("hr_records")
        assert deactivated is not None and deactivated.is_active is False

        assert len(await service.list_activities()) == len(DEFAULT_ACTIVITIES)
        active = await service.list_activities(active_only=True)
        assert "hr_records" not in {row.code for row in active}

    async def test_unknown_category_is_rejected(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="pdn-reg-c", session=test_db_session)
        service = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))

        with pytest.raises(InvalidRegistryValueError):
            await service.upsert(
                code="x",
                name="X",
                purpose="employment",
                legal_basis="consent",
                data_categories=["genetic"],
                subject_categories=["employees"],
            )

    async def test_registry_is_isolated_between_tenants(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(slug="pdn-reg-d", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="pdn-reg-e", session=test_db_session)
        await PdnProcessingRegistryService(
            test_db_session, tenant_id=str(tenant_a.id)
        ).seed_defaults()

        other = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant_b.id))
        assert await other.list_activities() == []


@pytest.mark.anyio
class TestProcessingAgreements:
    async def test_uncovered_activities_answer_who_is_responsible(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="pdn-dpa-a", session=test_db_session)
        registry = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))
        await registry.seed_defaults()
        agreements = PdnAgreementService(test_db_session, tenant_id=str(tenant.id))

        # Без договоров не покрыт ни один процесс.
        assert await agreements.uncovered_activity_codes() == sorted(
            a.code for a in DEFAULT_ACTIVITIES
        )

        await agreements.create(
            kind="rent",
            party_role="operator",
            counterparty_name="ООО Платформа",
            status="active",
            covered_activity_codes=["hr_records", "medical_exams"],
        )
        remaining = await agreements.uncovered_activity_codes()
        assert "hr_records" not in remaining and "medical_exams" not in remaining
        assert "training" in remaining

    async def test_draft_agreement_does_not_cover_anything(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Непод��исанный черновик не распределяет ответственность."""

        tenant = await data_factory.ensure_tenant(slug="pdn-dpa-b", session=test_db_session)
        registry = PdnProcessingRegistryService(test_db_session, tenant_id=str(tenant.id))
        await registry.seed_defaults()
        agreements = PdnAgreementService(test_db_session, tenant_id=str(tenant.id))

        await agreements.create(
            kind="outsourcing",
            party_role="processor",
            counterparty_name="ООО Клиент",
            status="draft",
            covered_activity_codes=["hr_records"],
        )
        assert "hr_records" in await agreements.uncovered_activity_codes()

    async def test_terminate_keeps_the_row_and_stops_covering(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="pdn-dpa-c", session=test_db_session)
        await PdnProcessingRegistryService(
            test_db_session, tenant_id=str(tenant.id)
        ).seed_defaults()
        agreements = PdnAgreementService(test_db_session, tenant_id=str(tenant.id))
        created = await agreements.create(
            kind="reseller",
            party_role="processor",
            counterparty_name="ООО Реселлер",
            status="active",
            covered_activity_codes=["training"],
        )

        terminated = await agreements.terminate(str(created.id))

        assert terminated is not None
        assert terminated.status == "terminated"
        assert terminated.terminated_at is not None
        assert len(await agreements.list_agreements()) == 1, "расторжение не должно удалять"
        assert "training" in await agreements.uncovered_activity_codes()

    async def test_unknown_kind_is_rejected(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant = await data_factory.ensure_tenant(slug="pdn-dpa-d", session=test_db_session)
        service = PdnAgreementService(test_db_session, tenant_id=str(tenant.id))
        with pytest.raises(InvalidRegistryValueError):
            await service.create(
                kind="franchise", party_role="operator", counterparty_name="X"
            )


@pytest.mark.anyio
class TestRegistryEndpoints:
    async def test_seed_list_deactivate_roundtrip(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        base = f"{API_PREFIX}/privacy/processing-activities"

        seeded = await async_client.post(f"{base}/seed-defaults", headers=headers)
        assert seeded.status_code == status.HTTP_200_OK, seeded.text
        body = seeded.json()
        assert body["total"] >= len(DEFAULT_ACTIVITIES)
        assert body["has_special_categories"] is True

        listed = await async_client.get(base, params={"active_only": True}, headers=headers)
        assert listed.status_code == status.HTTP_200_OK, listed.text
        codes = {item["code"] for item in listed.json()["items"]}
        assert {"hr_records", "medical_exams", "training"} <= codes

        gone = await async_client.delete(f"{base}/hr_records", headers=headers)
        assert gone.status_code == status.HTTP_200_OK, gone.text
        assert gone.json()["is_active"] is False

    async def test_upsert_updates_by_code(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        base = f"{API_PREFIX}/privacy/processing-activities"
        payload = {
            "code": "visitors_log",
            "name": "Журнал посетителей",
            "purpose": "occupational_safety",
            "legal_basis": "legal_obligation",
            "data_categories": ["regular"],
            "subject_categories": ["visitors"],
            "retention_months": 12,
        }

        first = await async_client.put(base, json=payload, headers=headers)
        assert first.status_code == status.HTTP_200_OK, first.text

        second = await async_client.put(
            base, json={**payload, "retention_months": 24}, headers=headers
        )
        assert second.status_code == status.HTTP_200_OK, second.text
        assert second.json()["id"] == first.json()["id"], "код процесса — естественный ключ"
        assert second.json()["retention_months"] == 24

    async def test_invalid_category_is_422(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        response = await async_client.put(
            f"{API_PREFIX}/privacy/processing-activities",
            json={
                "code": "bad",
                "name": "Bad",
                "purpose": "employment",
                "data_categories": ["genetic"],
                "subject_categories": ["employees"],
            },
            headers=_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text

    async def test_agreement_endpoints_report_uncovered(
        self, async_client: AsyncClient, make_auth_headers
    ) -> None:
        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        await async_client.post(
            f"{API_PREFIX}/privacy/processing-activities/seed-defaults", headers=headers
        )

        created = await async_client.post(
            f"{API_PREFIX}/privacy/agreements",
            json={
                "kind": "rent",
                "party_role": "operator",
                "counterparty_name": "ООО Платформа",
                "status": "active",
                "covered_activity_codes": ["hr_records"],
                "breach_notification_hours": 24,
            },
            headers=headers,
        )
        assert created.status_code == status.HTTP_201_CREATED, created.text

        listed = await async_client.get(f"{API_PREFIX}/privacy/agreements", headers=headers)
        assert listed.status_code == status.HTTP_200_OK, listed.text
        body = listed.json()
        assert body["total"] >= 1
        assert "hr_records" not in body["uncovered_activity_codes"]
        assert "medical_exams" in body["uncovered_activity_codes"]

        terminated = await async_client.post(
            f"{API_PREFIX}/privacy/agreements/{created.json()['id']}/terminate", headers=headers
        )
        assert terminated.status_code == status.HTTP_200_OK, terminated.text
        assert terminated.json()["status"] == "terminated"
