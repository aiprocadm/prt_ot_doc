"""SEC-66 срез-1 (разд. 66.2): права субъекта ПДн — выгрузка и журнал доступа."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature import Feature, FeatureEnablement
from app.models.models import MedicalExam, RoleEnum
from app.models.privacy import PdnAccessLog
from app.modules.privacy.service import (
    PDN_EXPORT_MAX_ITEMS,
    PDN_FEATURE_CODE,
    PdnAccessJournal,
    PdnSubjectExportService,
)
from app.services.employee_card import EmployeeCardService
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _headers(base: dict[str, str]) -> dict[str, str]:
    """Карточка/приватность требуют X-Tenant-Id (см. tests/test_employee_card.py)."""

    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


async def _disable_feature(session: AsyncSession, tenant_id: str) -> None:
    feature = (
        await session.execute(select(Feature).where(Feature.code == PDN_FEATURE_CODE))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code=PDN_FEATURE_CODE, title="PDn subject rights")
        session.add(feature)
        await session.flush()
    session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=False))
    await session.commit()


@pytest.mark.anyio
class TestPdnSubjectExportService:
    async def test_returns_none_for_unknown_subject(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        service = PdnSubjectExportService(tenant_id=str(tenant.id), session=test_db_session)
        assert await service.build("00000000-0000-0000-0000-000000000000") is None

    async def test_isolates_other_tenants(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(slug="pdn-tenant-a", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="pdn-tenant-b", session=test_db_session)
        company = await data_factory.create_company(tenant=tenant_a, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant_a,
            company=company,
            session=test_db_session,
            first_name="Cross",
            last_name="Pdn",
            email="cross-pdn@example.com",
        )

        foreign = PdnSubjectExportService(tenant_id=str(tenant_b.id), session=test_db_session)
        assert await foreign.build(person.id) is None

        own = PdnSubjectExportService(tenant_id=str(tenant_a.id), session=test_db_session)
        export = await own.build(person.id)
        assert export is not None
        assert export.subject.person_id == person.id
        assert export.max_items_per_section == PDN_EXPORT_MAX_ITEMS

    async def test_flags_special_category_when_medicals_present(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Health",
            last_name="Subject",
            email="health-subject@example.com",
        )

        service = PdnSubjectExportService(tenant_id=str(tenant.id), session=test_db_session)
        export = await service.build(person.id)
        assert export is not None
        assert export.data_categories == ["regular"]

        today = date.today()
        test_db_session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=today - timedelta(days=10),
                valid_until=today + timedelta(days=355),
                conclusion="fit",
            )
        )
        await test_db_session.commit()

        export = await service.build(person.id)
        assert export is not None
        # Здоровье — специальная категория ПДн (разд. 66.1).
        assert export.data_categories == ["regular", "special_health"]
        assert export.truncated is False

    async def test_export_limit_is_higher_than_card_limit(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        """Механика обрезки: счётчик секции полный, список — ограничен пределом."""

        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Many",
            last_name="Exams",
            email="many-exams@example.com",
        )
        today = date.today()
        for offset in range(3):
            test_db_session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=today - timedelta(days=30 * offset + 1),
                    valid_until=today + timedelta(days=300 - offset),
                    conclusion="fit",
                )
            )
        await test_db_session.commit()

        capped = EmployeeCardService(
            tenant_id=str(tenant.id), db=test_db_session, max_items_per_section=2
        )
        card = await capped.build(person.id)
        assert card is not None
        assert card.medicals.count == 3
        assert len(card.medicals.items) == 2

        # Выгрузка ПДн с потолком 1000 отдаёт всё и не помечает себя обрезанной.
        export = await PdnSubjectExportService(
            tenant_id=str(tenant.id), session=test_db_session
        ).build(person.id)
        assert export is not None
        assert len(export.data.medicals.items) == 3
        assert export.truncated is False


@pytest.mark.anyio
class TestPdnAccessJournal:
    async def test_records_and_lists_by_subject(
        self,
        test_db_session: AsyncSession,
        data_factory: TestDataFactory,
    ) -> None:
        tenant = await data_factory.ensure_tenant(session=test_db_session)
        company = await data_factory.create_company(tenant=tenant, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Journal",
            last_name="Subject",
            email="journal-subject@example.com",
        )
        other = await data_factory.create_person(
            tenant=tenant,
            company=company,
            session=test_db_session,
            first_name="Other",
            last_name="Subject",
            email="other-subject@example.com",
        )

        journal = PdnAccessJournal(test_db_session)
        await journal.record(
            tenant_id=str(tenant.id),
            subject_person_id=person.id,
            action="export",
            actor_email="dpo@example.com",
            purpose="запрос субъекта",
        )
        await journal.record(
            tenant_id=str(tenant.id),
            subject_person_id=other.id,
            action="view_card",
            actor_email="hr@example.com",
        )
        await test_db_session.commit()

        rows, total = await journal.list_for_subject(
            tenant_id=str(tenant.id), subject_person_id=person.id
        )
        assert total == 1
        assert len(rows) == 1
        assert rows[0].action == "export"
        assert rows[0].purpose == "запрос субъекта"


@pytest.mark.anyio
class TestPdnSubjectRightsEndpoints:
    async def test_export_returns_data_and_writes_journal(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Export",
                last_name="Subject",
                email="export-subject@example.com",
            )
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/{person.id}/export",
            params={"purpose": "обращение субъекта"},
            headers=headers,
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["subject"]["person_id"] == person.id
        assert body["data"]["person_id"] == person.id
        assert body["format_version"] == "1.0"

        # Само обращение немедленно видно в журнале доступа субъекта.
        log_response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/{person.id}/access-log", headers=headers
        )
        assert log_response.status_code == status.HTTP_200_OK, log_response.text
        log_body = log_response.json()
        assert log_body["total"] >= 1
        exports = [item for item in log_body["items"] if item["action"] == "export"]
        assert exports, log_body
        assert exports[0]["purpose"] == "обращение субъекта"

        async with sessionmaker() as session:
            persisted = (
                (
                    await session.execute(
                        select(PdnAccessLog).where(PdnAccessLog.subject_person_id == person.id)
                    )
                )
                .scalars()
                .all()
            )
        assert [row.action for row in persisted] == ["export"]

    async def test_employee_card_read_is_journalled(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Card",
                last_name="Watched",
                email="card-watched@example.com",
            )
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        card_response = await async_client.get(
            f"{API_PREFIX}/employees/{person.id}", headers=headers
        )
        assert card_response.status_code == status.HTTP_200_OK, card_response.text

        log_response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/{person.id}/access-log", headers=headers
        )
        assert log_response.status_code == status.HTTP_200_OK, log_response.text
        actions = [item["action"] for item in log_response.json()["items"]]
        assert "view_card" in actions

    async def test_unknown_subject_returns_404(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            await data_factory.ensure_tenant(session=session)
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/00000000-0000-0000-0000-000000000000/export",
            headers=headers,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_card_reader_role_cannot_export(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """`ot_pb_lead` читает карточку сотрудника, но выгружать ПДн ему нельзя."""

        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Narrow",
                last_name="Rbac",
                email="narrow-rbac@example.com",
            )
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.OT_PB_LEAD))
        card_response = await async_client.get(
            f"{API_PREFIX}/employees/{person.id}", headers=headers
        )
        assert card_response.status_code == status.HTTP_200_OK, card_response.text

        export_response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/{person.id}/export", headers=headers
        )
        assert export_response.status_code in {
            status.HTTP_403_FORBIDDEN,
            status.HTTP_401_UNAUTHORIZED,
        }

    async def test_404_when_feature_disabled(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            person = await data_factory.create_person(
                tenant=tenant,
                company=company,
                session=session,
                first_name="Disabled",
                last_name="Feature",
                email="disabled-feature@example.com",
            )
            await _disable_feature(session, str(tenant.id))

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.get(
            f"{API_PREFIX}/privacy/subjects/{person.id}/export", headers=headers
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
