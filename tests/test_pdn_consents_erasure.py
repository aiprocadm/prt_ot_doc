"""SEC-66 срез-2 (разд. 66.1 и 66.2): согласия субъекта и обезличивание.

Что здесь закрепляется:

* согласия **версионируются, а не редактируются** — иначе нечем доказать
  правомерность обработки, которая шла до перевыдачи;
* отзыв согласия **не обязывает** стирать данные, обрабатываемые по другому
  основанию (трудовой договор, требование закона) — сервис сообщает, какие
  основания остались, и решение принимает оператор;
* обезличивание **необратимо и идемпотентно**, вычищает прямые идентификаторы и
  СОХРАНЯЕТ связанные записи (медосмотры/СИЗ/обучение), сроки хранения которых
  предписаны законом;
* всё это попадает в журнал доступа к ПДн — обращение без следа нарушает разд. 66.2.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Person
from app.models.models import RoleEnum
from app.models.privacy import PdnAccessLog
from app.models.privacy_consents import PdnConsent, PdnErasureRecord
from app.modules.privacy.consents import (
    PdnConsentService,
    PdnErasureService,
    UnknownLegalBasisError,
    UnknownPurposeError,
)
from tests.utils.factories import TestDataFactory

API_PREFIX = "/api/v1"


def _headers(base: dict[str, str]) -> dict[str, str]:
    """Контур приватности требует X-Tenant-Id (см. tests/test_pdn_subject_rights.py)."""

    merged = {**base}
    tid = merged.get("x-tenant") or merged.get("X-Tenant-Id")
    if tid:
        merged.setdefault("X-Tenant-Id", str(tid))
    return merged


async def _subject(data_factory: TestDataFactory, session: AsyncSession, **kwargs):
    tenant = await data_factory.ensure_tenant(session=session)
    company = await data_factory.create_company(tenant=tenant, session=session)
    person = await data_factory.create_person(
        tenant=tenant, company=company, session=session, **kwargs
    )
    return tenant, person


@pytest.mark.anyio
class TestConsentVersioning:
    async def test_regrant_creates_new_version_and_supersedes_previous(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnConsentService(test_db_session, tenant_id=str(tenant.id))

        first = await service.grant(person_id=str(person.id), purpose="medical_exams")
        second = await service.grant(person_id=str(person.id), purpose="medical_exams")

        assert (first.consent_version, second.consent_version) == (1, 2)
        assert second.status == "active"
        # Прежняя версия сохранена, но больше не действует: историю нельзя терять,
        # иначе не доказать правомерность обработки до перевыдачи.
        assert first.status == "superseded"

        active = await service.active_for_subject(str(person.id))
        assert [c.id for c in active] == [second.id]

    async def test_withdraw_keeps_the_row(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnConsentService(test_db_session, tenant_id=str(tenant.id))
        await service.grant(person_id=str(person.id), purpose="training")

        withdrawn = await service.withdraw(
            person_id=str(person.id), purpose="training", reason="отзыв субъекта"
        )

        assert withdrawn is not None
        assert withdrawn.status == "withdrawn"
        assert withdrawn.withdrawn_at is not None
        assert withdrawn.withdrawal_reason == "отзыв субъекта"
        rows = (
            (await test_db_session.execute(select(PdnConsent))).scalars().all()
        )
        assert len(rows) == 1, "отзыв не должен удалять строку"

    async def test_withdraw_without_active_consent_returns_none(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnConsentService(test_db_session, tenant_id=str(tenant.id))
        assert await service.withdraw(person_id=str(person.id), purpose="training") is None

    async def test_remaining_bases_survive_withdrawal_of_one_purpose(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Юридическая суть: отзыв согласия ≠ обязанность стереть всё."""

        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnConsentService(test_db_session, tenant_id=str(tenant.id))
        await service.grant(person_id=str(person.id), purpose="medical_exams")
        await service.grant(
            person_id=str(person.id), purpose="employment", legal_basis="contract"
        )

        await service.withdraw(person_id=str(person.id), purpose="medical_exams")

        assert await service.remaining_legal_bases(str(person.id)) == ["contract"]

    async def test_unknown_vocabulary_is_rejected(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnConsentService(test_db_session, tenant_id=str(tenant.id))

        with pytest.raises(UnknownPurposeError):
            await service.grant(person_id=str(person.id), purpose="marketing")
        with pytest.raises(UnknownLegalBasisError):
            await service.grant(
                person_id=str(person.id), purpose="training", legal_basis="because"
            )

    async def test_consents_are_isolated_between_tenants(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant_a = await data_factory.ensure_tenant(slug="pdn-c-a", session=test_db_session)
        tenant_b = await data_factory.ensure_tenant(slug="pdn-c-b", session=test_db_session)
        company = await data_factory.create_company(tenant=tenant_a, session=test_db_session)
        person = await data_factory.create_person(
            tenant=tenant_a, company=company, session=test_db_session
        )
        await PdnConsentService(test_db_session, tenant_id=str(tenant_a.id)).grant(
            person_id=str(person.id), purpose="training"
        )

        other = PdnConsentService(test_db_session, tenant_id=str(tenant_b.id))
        assert await other.list_for_subject(str(person.id)) == []


@pytest.mark.anyio
class TestErasure:
    async def test_scrubs_identifiers_and_keeps_related_records(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        tenant, person = await _subject(
            data_factory,
            test_db_session,
            first_name="Иван",
            last_name="Петров",
            email="ivan@example.com",
        )
        person.snils = "123-456-789 00"
        person.passport = "4509 123456"
        person.phone = "+7 900 000-00-00"
        person.personnel_number = "TAB-1"
        await test_db_session.flush()

        outcome = await PdnErasureService(test_db_session, tenant_id=str(tenant.id)).anonymize(
            person, reason="запрос субъекта"
        )

        assert outcome.already_anonymized is False
        assert person.anonymized_at is not None
        for field in ("email", "phone", "snils", "passport", "personnel_number", "birth_date"):
            assert getattr(person, field) is None, field
        # Псевдоним, а не пустая строка: обезличенные записи должны оставаться
        # связываемыми между собой, не восстанавливая личность.
        assert person.last_name == outcome.record.pseudonym
        assert outcome.record.pseudonym.startswith("subject-")
        # Запись доказывает, что именно было вычищено.
        assert outcome.record.scrubbed_fields["snils"] is True
        assert outcome.record.scrubbed_fields["middle_name"] is False
        # И что сохранено обезличенным (сроки хранения по закону).
        assert set(outcome.record.retained_sections) == {
            "medical_exams",
            "ppe_issues",
            "training_sessions",
        }

    async def test_is_idempotent(
        self, test_db_session: AsyncSession, data_factory: TestDataFactory
    ) -> None:
        """Повтор запроса субъекта не должен выглядеть как второе обезличивание."""

        tenant, person = await _subject(data_factory, test_db_session)
        service = PdnErasureService(test_db_session, tenant_id=str(tenant.id))

        first = await service.anonymize(person, reason="раз")
        second = await service.anonymize(person, reason="два")

        assert second.already_anonymized is True
        assert second.record.id == first.record.id
        records = (await test_db_session.execute(select(PdnErasureRecord))).scalars().all()
        assert len(records) == 1


@pytest.mark.anyio
class TestPdnConsentAndErasureEndpoints:
    async def test_grant_list_withdraw_roundtrip(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            _, person = await _subject(data_factory, session)
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        base = f"{API_PREFIX}/privacy/subjects/{person.id}/consents"

        granted = await async_client.post(
            base,
            json={"purpose": "medical_exams", "legal_basis": "consent", "document_ref": "acme-1"},
            headers=headers,
        )
        assert granted.status_code == status.HTTP_201_CREATED, granted.text
        assert granted.json()["version"] == 1

        listed = await async_client.get(base, headers=headers)
        assert listed.status_code == status.HTTP_200_OK, listed.text
        assert listed.json()["remaining_legal_bases"] == ["consent"]

        withdrawn = await async_client.post(
            f"{base}/withdraw",
            json={"purpose": "medical_exams", "reason": "отзыв"},
            headers=headers,
        )
        assert withdrawn.status_code == status.HTTP_200_OK, withdrawn.text
        assert withdrawn.json()["status"] == "withdrawn"

        after = await async_client.get(base, headers=headers)
        assert after.json()["remaining_legal_bases"] == []

    async def test_unknown_purpose_is_422_not_500(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            _, person = await _subject(data_factory, session)
            await session.commit()

        response = await async_client.post(
            f"{API_PREFIX}/privacy/subjects/{person.id}/consents",
            json={"purpose": "marketing"},
            headers=_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, response.text

    async def test_anonymize_endpoint_scrubs_and_journals(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            _, person = await _subject(
                data_factory, session, first_name="Удаляемый", last_name="Субъект"
            )
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        response = await async_client.post(
            f"{API_PREFIX}/privacy/subjects/{person.id}/anonymize",
            json={"reason": "запрос субъекта"},
            headers=headers,
        )
        assert response.status_code == status.HTTP_200_OK, response.text
        body = response.json()
        assert body["already_anonymized"] is False
        assert body["pseudonym"].startswith("subject-")

        async with sessionmaker() as session:
            stored = (
                await session.execute(select(Person).where(Person.id == person.id))
            ).scalar_one()
            assert stored.anonymized_at is not None
            assert stored.email is None
            logged = (
                (
                    await session.execute(
                        select(PdnAccessLog).where(
                            PdnAccessLog.subject_person_id == person.id,
                            PdnAccessLog.action == "anonymize",
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(logged) == 1, "обезличивание обязано оставлять след в журнале"

    async def test_unknown_subject_is_404(
        self,
        async_client: AsyncClient,
        make_auth_headers,
    ) -> None:
        response = await async_client.post(
            f"{API_PREFIX}/privacy/subjects/00000000-0000-0000-0000-000000000000/anonymize",
            json={},
            headers=_headers(await make_auth_headers(RoleEnum.ADMIN)),
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, response.text


@pytest.mark.anyio
class TestRectificationJournalling:
    async def test_pii_edit_is_journalled_and_no_op_edit_is_not(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        async with sessionmaker() as session:
            _, person = await _subject(
                data_factory, session, first_name="Пётр", last_name="Сидоров"
            )
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        url = f"{API_PREFIX}/persons/{person.id}"

        changed = await async_client.patch(url, json={"phone": "+7 999 111-22-33"}, headers=headers)
        assert changed.status_code == status.HTTP_200_OK, changed.text

        # Повторная отправка того же значения ничего не меняет — журнал субъекта не
        # должен зашумляться записями «правил, но не изменил».
        repeat = await async_client.patch(url, json={"phone": "+7 999 111-22-33"}, headers=headers)
        assert repeat.status_code == status.HTTP_200_OK, repeat.text

        async with sessionmaker() as session:
            entries = (
                (
                    await session.execute(
                        select(PdnAccessLog).where(
                            PdnAccessLog.subject_person_id == person.id,
                            PdnAccessLog.action == "rectify",
                        )
                    )
                )
                .scalars()
                .all()
            )
        assert len(entries) == 1, [e.purpose for e in entries]
        assert "phone" in (entries[0].purpose or "")

    async def test_anonymized_subject_cannot_be_re_identified(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        sessionmaker,
        data_factory: TestDataFactory,
    ) -> None:
        """Без этой проверки «право на удаление» отменяется одним PATCH."""

        async with sessionmaker() as session:
            _, person = await _subject(data_factory, session)
            await session.commit()

        headers = _headers(await make_auth_headers(RoleEnum.ADMIN))
        anonymized = await async_client.post(
            f"{API_PREFIX}/privacy/subjects/{person.id}/anonymize", json={}, headers=headers
        )
        assert anonymized.status_code == status.HTTP_200_OK, anonymized.text

        restored = await async_client.patch(
            f"{API_PREFIX}/persons/{person.id}",
            json={"first_name": "Иван", "snils": "111-222-333 44"},
            headers=headers,
        )
        assert restored.status_code == status.HTTP_409_CONFLICT, restored.text

        # Неперсональные поля править по-прежнему можно: обезличенная запись
        # остаётся рабочей единицей учёта по охране труда.
        non_pii = await async_client.patch(
            f"{API_PREFIX}/persons/{person.id}",
            json={"working_conditions_class": "3.1"},
            headers=headers,
        )
        assert non_pii.status_code == status.HTTP_200_OK, non_pii.text
