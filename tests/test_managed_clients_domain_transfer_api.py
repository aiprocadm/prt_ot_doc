"""BIZ-49 срез-15 — перенос доменной истории людей (разд. 49.1).

Проверяется то, что нельзя увидеть в счётчиках: КУДА показывают ссылки у
копий. Копия, сохранившая ссылку на каталог или пользователя аутсорсера, —
не «мелочь», а дыра изоляции между арендаторами.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.master_data import Company, Person
from app.models.medical import (
    MedicalExam,
    MedicalExamKind,
    MedicalReferral,
    MedicalSuspension,
    MedicalSuspensionReason,
)
from app.models.models import Tenant
from app.models.ppe import PPEIssue, PPEItem
from app.models.training import (
    Training,
    TrainingCertificate,
    TrainingCourse,
    TrainingProgram,
    TrainingSession,
    TrainingStatus,
)

_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 8, 8)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="admin-1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["admin"], company_id=None)


def _request():
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


class _TrustedWrapper:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._orig_commit = self._session.commit
        self._session.commit = self._session.flush
        return self._session

    async def __aexit__(self, *exc):
        self._session.commit = self._orig_commit
        return False


async def _setup(session):
    """Клиент в режиме Dedicated + его организация + один сотрудник."""

    company = Company(tenant_id=_TENANT, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    session.add(
        Tenant(
            slug="romashka",
            code="romashka",
            name="Ромашка",
            schema_name="tenant_romashka",
            contact_email="r@r.ru",
        )
    )
    client = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        company_id=company.id,
        dedicated_tenant_slug="romashka",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    person = Person(
        tenant_id=_TENANT,
        company_id=company.id,
        first_name="Иван",
        last_name="Иванов",
        position_title="Слесарь",
    )
    session.add(person)
    await session.flush()
    return client, company, person


async def _transfer(session, mcid):
    with patch.object(routes, "_trusted_session", lambda: _TrustedWrapper(session)):
        return await routes.transfer_client_data(
            mcid=mcid,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )


async def _target_id(session) -> str:
    row = (await session.execute(select(Tenant).where(Tenant.slug == "romashka"))).scalar_one()
    return row.id


# --- медосмотры -------------------------------------------------------------
@pytest.mark.asyncio
async def test_medical_history_is_copied_with_remapped_links(sessionmaker):
    """Цикл exam ↔ referral обязан сшиться на НОВЫЕ id, а не на исходные."""

    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        referral = MedicalReferral(
            tenant_id=_TENANT,
            person_id=person.id,
            exam_kind=MedicalExamKind.PERIODIC,
            medical_org_name="Клиника",
            # Пользователь аутсорсера: в арендаторе клиента его нет.
            issued_by=None,
        )
        session.add(referral)
        await session.flush()
        exam = MedicalExam(
            tenant_id=_TENANT,
            person_id=person.id,
            exam_type="периодический",
            exam_date=_TODAY,
            valid_until=date(2027, 8, 8),
            referral_id=referral.id,
        )
        session.add(exam)
        await session.flush()
        referral.result_exam_id = exam.id
        session.add(
            MedicalSuspension(
                tenant_id=_TENANT,
                person_id=person.id,
                reason=MedicalSuspensionReason.UNFIT,
                source_exam_id=exam.id,
                started_at=_NOW,
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["medical_exams"] == 1
        assert out.counts["medical_referrals"] == 1
        assert out.counts["medical_suspensions"] == 1

        target = await _target_id(session)
        new_person = (
            await session.execute(select(Person).where(Person.tenant_id == target))
        ).scalar_one()
        new_exam = (
            await session.execute(select(MedicalExam).where(MedicalExam.tenant_id == target))
        ).scalar_one()
        new_referral = (
            await session.execute(
                select(MedicalReferral).where(MedicalReferral.tenant_id == target)
            )
        ).scalar_one()
        new_susp = (
            await session.execute(
                select(MedicalSuspension).where(MedicalSuspension.tenant_id == target)
            )
        ).scalar_one()

        assert new_exam.person_id == new_person.id
        # Ссылки сшиты на копии, а НЕ на строки аутсорсера.
        assert new_exam.referral_id == new_referral.id
        assert new_referral.result_exam_id == new_exam.id
        assert new_susp.source_exam_id == new_exam.id
        assert new_exam.exam_date == _TODAY  # смысловые даты сохранены


@pytest.mark.asyncio
async def test_deleted_domain_rows_are_not_copied(sessionmaker):
    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        session.add(
            MedicalExam(
                tenant_id=_TENANT,
                person_id=person.id,
                exam_type="удалённый",
                exam_date=_TODAY,
                valid_until=date(2027, 1, 1),
                deleted_at=_NOW,
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["medical_exams"] == 0


@pytest.mark.asyncio
async def test_other_company_people_history_stays(sessionmaker):
    """Люди другой организации аутсорсера не переносятся — и их история тоже."""

    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        other_company = Company(tenant_id=_TENANT, name="ООО Чужая")
        session.add(other_company)
        await session.flush()
        stranger = Person(
            tenant_id=_TENANT,
            company_id=other_company.id,
            first_name="Пётр",
            last_name="Чужой",
        )
        session.add(stranger)
        await session.flush()
        session.add(
            MedicalExam(
                tenant_id=_TENANT,
                person_id=stranger.id,
                exam_type="чужой",
                exam_date=_TODAY,
                valid_until=date(2027, 1, 1),
            )
        )
        session.add(
            MedicalExam(
                tenant_id=_TENANT,
                person_id=person.id,
                exam_type="свой",
                exam_date=_TODAY,
                valid_until=date(2027, 1, 1),
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["medical_exams"] == 1

        target = await _target_id(session)
        copied = (
            (await session.execute(select(MedicalExam).where(MedicalExam.tenant_id == target)))
            .scalars()
            .all()
        )
        assert [e.exam_type for e in copied] == ["свой"]


# --- СИЗ --------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ppe_issues_copied_without_catalog_and_with_remapped_chain(sessionmaker):
    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        item = PPEItem(tenant_id=_TENANT, name="Каска")
        # Вторая позиция каталога никому из переносимых людей не выдавалась —
        # она обязана остаться у аутсорсера.
        unused = PPEItem(tenant_id=_TENANT, name="Респиратор")
        session.add_all([item, unused])
        await session.flush()
        first = PPEIssue(
            tenant_id=_TENANT,
            person_id=person.id,
            item_id=item.id,
            item_name="Каска",
            quantity=1,
            issued_at=_NOW,
        )
        session.add(first)
        await session.flush()
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id=person.id,
                item_id=item.id,
                item_name="Каска",
                quantity=1,
                issued_at=_NOW,
                replaces_issue_id=first.id,
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["ppe_issues"] == 2

        target = await _target_id(session)
        copies = (
            (await session.execute(select(PPEIssue).where(PPEIssue.tenant_id == target)))
            .scalars()
            .all()
        )
        assert len(copies) == 2
        assert all(c.item_name == "Каска" for c in copies)
        # Переехала ТОЛЬКО использованная карточка номенклатуры, а не каталог:
        # без неё замена скопированной выдачи отвергалась бы API.
        items = (
            (await session.execute(select(PPEItem).where(PPEItem.tenant_id == target)))
            .scalars()
            .all()
        )
        assert [i.name for i in items] == ["Каска"]
        assert out.counts["ppe_items"] == 1
        # Выдачи ссылаются на КОПИЮ карточки, а не на номенклатуру аутсорсера.
        assert all(c.item_id == items[0].id for c in copies)
        # Цепочка замены перевешена на копию, а не на id аутсорсера.
        chained = [c for c in copies if c.replaces_issue_id is not None]
        assert len(chained) == 1
        assert chained[0].replaces_issue_id in {c.id for c in copies}


# --- обучение ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_training_history_copied_with_course_cards(sessionmaker):
    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        course = TrainingCourse(
            tenant_id=_TENANT,
            title="Работа на высоте",
            code="ВЫС-1",
            description="Программа курса",
            duration_hours=16,
        )
        program = TrainingProgram(
            tenant_id=_TENANT,
            code="ПРГ-1",
            title="Программа 46н",
            category="ot",
            kind="program",
            owner_user_id="user-of-outsourcer",
        )
        session.add_all([course, program])
        await session.flush()
        session.add(
            Training(
                tenant_id=_TENANT,
                person_id=person.id,
                course_name="Легаси-курс",
                status=TrainingStatus.COMPLETED,
            )
        )
        session.add(
            TrainingSession(
                tenant_id=_TENANT,
                person_id=person.id,
                course_id=course.id,
            )
        )
        session.add(
            TrainingCertificate(
                tenant_id=_TENANT,
                person_id=person.id,
                training_program_id=program.id,
                code="УД-1",
                issued_at=_TODAY,
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["trainings_legacy"] == 1
        assert out.counts["training_sessions"] == 1
        assert out.counts["training_certificates"] == 1
        assert out.counts["training_courses"] == 1
        assert out.counts["training_programs"] == 1

        target = await _target_id(session)
        new_course = (
            await session.execute(select(TrainingCourse).where(TrainingCourse.tenant_id == target))
        ).scalar_one()
        new_session = (
            await session.execute(
                select(TrainingSession).where(TrainingSession.tenant_id == target)
            )
        ).scalar_one()
        new_program = (
            await session.execute(
                select(TrainingProgram).where(TrainingProgram.tenant_id == target)
            )
        ).scalar_one()
        new_cert = (
            await session.execute(
                select(TrainingCertificate).where(TrainingCertificate.tenant_id == target)
            )
        ).scalar_one()

        # Сессия ссылается на КОПИЮ карточки курса, план не переносится.
        assert new_session.course_id == new_course.id
        assert new_session.plan_id is None
        assert new_course.title == "Работа на высоте"
        # Владелец программы — пользователь аутсорсера, ссылка снята.
        assert new_program.owner_user_id is None
        assert new_cert.training_program_id == new_program.id
        # Файл удостоверения остаётся в хранилище аутсорсера.
        assert new_cert.file_id is None


# --- регрессы по находкам ревью ---------------------------------------------
@pytest.mark.asyncio
async def test_copies_keep_original_service_timestamps(sessionmaker):
    """Карточка 766н читает updated_at выдачи как дату события «списан/заменён».

    Копия со «свежим» updated_at показала бы, что всё это случилось в день
    переноса, — история поехала бы.
    """

    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        old = datetime(2025, 3, 1, 10, 0, tzinfo=timezone.utc)
        issue = PPEIssue(
            tenant_id=_TENANT,
            person_id=person.id,
            item_name="Каска",
            quantity=1,
            issued_at=old,
            status="written_off",
            created_at=old,
            updated_at=old,
        )
        session.add(issue)
        await session.flush()

        await _transfer(session, client.id)

        target = await _target_id(session)
        copy = (
            await session.execute(select(PPEIssue).where(PPEIssue.tenant_id == target))
        ).scalar_one()

        # SQLite отдаёт datetime без часового пояса (грабля среза-6) —
        # сравниваем нормализованно, проверяется именно СОХРАНЕНИЕ момента.
        def _utc(value):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        assert _utc(copy.created_at) == old
        assert _utc(copy.updated_at) == old


@pytest.mark.asyncio
async def test_certificate_without_program_is_skipped_not_nulled(sessionmaker):
    """В БАЗЕ training_program_id NOT NULL, хотя модель говорит обратное.

    Копия с NULL прошла бы на SQLite и упала на PostgreSQL — поэтому такие
    удостоверения не переносятся вовсе и видны отдельным числом.
    """

    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        session.add(
            TrainingCertificate(
                tenant_id=_TENANT,
                person_id=person.id,
                training_program_id=None,
                code="БЕЗ-ПРОГРАММЫ",
                issued_at=_TODAY,
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        assert out.counts["training_certificates"] == 0
        assert out.counts["training_certificates_skipped"] == 1

        target = await _target_id(session)
        copied = (
            (
                await session.execute(
                    select(TrainingCertificate).where(TrainingCertificate.tenant_id == target)
                )
            )
            .scalars()
            .all()
        )
        assert copied == []


@pytest.mark.asyncio
async def test_json_fields_are_copied_by_value(sessionmaker):
    """JSON-колонки — MutableList/MutableDict: присвоение ссылкой отдало бы
    копии ТОТ ЖЕ объект, и правка у клиента меняла бы данные аутсорсера."""

    async with sessionmaker() as session:
        client, _company, person = await _setup(session)
        exam = MedicalExam(
            tenant_id=_TENANT,
            person_id=person.id,
            exam_type="периодический",
            exam_date=_TODAY,
            valid_until=date(2027, 1, 1),
            contraindications=["шум"],
        )
        session.add(exam)
        await session.flush()

        await _transfer(session, client.id)

        target = await _target_id(session)
        copy = (
            await session.execute(select(MedicalExam).where(MedicalExam.tenant_id == target))
        ).scalar_one()
        assert copy.contraindications == ["шум"]

        # Правка у клиента не должна отразиться у аутсорсера.
        copy.contraindications.append("вибрация")
        await session.flush()
        original = (
            await session.execute(select(MedicalExam).where(MedicalExam.id == exam.id))
        ).scalar_one()
        assert original.contraindications == ["шум"]


@pytest.mark.asyncio
async def test_left_behind_is_reported_as_numbers(sessionmaker):
    """Осознанно не перенесённое показывается числом, а не молчанием."""

    from app.models.document import Document

    async with sessionmaker() as session:
        client, company, person = await _setup(session)
        session.add(
            Document(
                tenant_id=_TENANT,
                company_id=company.id,
                person_id=person.id,
                template_id="tpl-1",
                created_by="admin-1",
            )
        )
        await session.flush()

        out = await _transfer(session, client.id)
        # Документы требуют шаблонов и копирования объектов хранилища —
        # отдельная работа; клиент видит её объём.
        assert out.counts["documents_left_behind"] == 1
        assert out.counts["permits_left_behind"] == 0
