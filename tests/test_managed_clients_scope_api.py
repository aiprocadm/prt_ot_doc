"""BIZ-49 срез-9 — контекст клиента как ФИЛЬТР данных (разд. 49.3).

Проверяется главное обещание индикатора «вы работаете от имени X»: в разделах,
которые он называет, видны данные ТОЛЬКО этого клиента.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes import persons as persons_routes
from app.api.routes.medical import exams as exams_routes
from app.domains.managed_clients.scope import ClientDataScope
from app.models.models import Company, MedicalExam, Person, Tenant
from app.schemas.person import PersonCreate, PersonUpdate

_SLUG = "test"


async def _tenant_id(session) -> str:
    """Реальный арендатор из фикстуры: репозиторий сверяет его с сессией."""

    return (await session.execute(select(Tenant).where(Tenant.slug == _SLUG))).scalars().one().id


def _tenant(tid):
    return SimpleNamespace(id=tid, is_active=True, slug=_SLUG, code=_SLUG)


def _request(headers=None):
    return SimpleNamespace(headers=headers or {})


def _response():
    return SimpleNamespace(headers={})


def _scope(company_id="co-a", *, reason=None):
    return ClientDataScope(
        client_id="mc1",
        client_name="ООО Ромашка",
        company_id=company_id,
        reason=reason,
    )


async def _company(session, tid, cid, name):
    row = Company(id=cid, tenant_id=tid, name=name, inn=f"77{cid}")
    session.add(row)
    await session.flush()
    return row


async def _person(session, tid, *, company_id, last_name):
    row = Person(
        tenant_id=tid,
        company_id=company_id,
        first_name="Иван",
        last_name=last_name,
    )
    session.add(row)
    await session.flush()
    return row


async def _exam(session, tid, *, person_id):
    row = MedicalExam(
        tenant_id=tid,
        person_id=person_id,
        exam_type="periodic",
        exam_date=date(2026, 1, 10),
        valid_until=date(2027, 1, 10),
    )
    session.add(row)
    await session.flush()
    return row


async def _two_clients(session):
    tid = await _tenant_id(session)
    await _company(session, tid, "co-a", "Ромашка")
    await _company(session, tid, "co-b", "Одуванчик")
    ours = await _person(session, tid, company_id="co-a", last_name="Наш")
    theirs = await _person(session, tid, company_id="co-b", last_name="Чужой")
    return tid, ours, theirs


async def _list_persons(session, tid, scope):
    return await persons_routes.list_persons_endpoint(
        request=_request(),
        response=_response(),
        tenant=_tenant(tid),
        session=session,
        access=SimpleNamespace(),
        scope=scope,
        correlation_id="c1",
        limit=50,
        offset=0,
        q=None,
    )


@pytest.mark.asyncio
async def test_persons_list_shows_only_the_client_in_context(sessionmaker):
    async with sessionmaker() as session:
        tid, _, _ = await _two_clients(session)

        page = await _list_persons(session, tid, _scope())

    names = {p.last_name for p in page.items}
    assert names == {"Наш"}
    assert page.total == 1


@pytest.mark.asyncio
async def test_persons_list_without_context_stays_unchanged(sessionmaker):
    """Без контекста ничего не меняется: обычная работа не должна пострадать."""

    async with sessionmaker() as session:
        tid, _, _ = await _two_clients(session)

        page = await _list_persons(session, tid, None)

    assert {p.last_name for p in page.items} == {"Наш", "Чужой"}


@pytest.mark.asyncio
async def test_persons_list_is_empty_when_client_data_lives_elsewhere(sessionmaker):
    """Свой контур клиента: пусто, а НЕ «все сотрудники аутсорсера»."""

    async with sessionmaker() as session:
        tid, _, _ = await _two_clients(session)

        page = await _list_persons(
            session, tid, _scope(None, reason="Данные ведутся в отдельном контуре")
        )

    assert page.items == []
    assert page.total == 0


@pytest.mark.asyncio
async def test_etag_does_not_leak_across_contexts(sessionmaker):
    """Кэш вне контекста не должен «возвращаться» 304-м ответом внутри него."""

    async with sessionmaker() as session:
        tid, _, _ = await _two_clients(session)

        outside = _response()
        await persons_routes.list_persons_endpoint(
            request=_request(),
            response=outside,
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=None,
            correlation_id="c1",
            limit=50,
            offset=0,
            q=None,
        )
        inside = _response()
        await persons_routes.list_persons_endpoint(
            request=_request(),
            response=inside,
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=_scope(),
            correlation_id="c1",
            limit=50,
            offset=0,
            q=None,
        )

    assert outside.headers["ETag"] != inside.headers["ETag"]


@pytest.mark.asyncio
async def test_foreign_person_is_not_found_not_forbidden(sessionmaker):
    """403 подтвердило бы существование записи — это уже утечка."""

    async with sessionmaker() as session:
        tid, _, theirs = await _two_clients(session)

        with pytest.raises(HTTPException) as exc:
            await persons_routes.get_person_endpoint(
                person_id=theirs.id,
                tenant=_tenant(tid),
                session=session,
                access=SimpleNamespace(),
                scope=_scope(),
                correlation_id="c1",
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_own_person_is_readable_in_context(sessionmaker):
    async with sessionmaker() as session:
        tid, ours, _ = await _two_clients(session)

        out = await persons_routes.get_person_endpoint(
            person_id=ours.id,
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=_scope(),
            correlation_id="c1",
        )

    assert out.last_name == "Наш"


@pytest.mark.asyncio
async def test_cannot_create_person_in_another_clients_company(sessionmaker, monkeypatch):
    """Самая дорогая ошибка аутсорсера — человек, заведённый не в ту организацию."""

    async with sessionmaker() as session:
        tid, _, _ = await _two_clients(session)
        monkeypatch.setattr(
            persons_routes.BillingService,
            "assert_allowed",
            _allow_billing,
            raising=False,
        )

        with pytest.raises(HTTPException) as exc:
            await persons_routes.create_person_endpoint(
                payload=PersonCreate(company_id="co-b", first_name="Пётр", last_name="Новый"),
                tenant=_tenant(tid),
                session=session,
                access=SimpleNamespace(),
                scope=_scope(),
                correlation_id="c1",
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_cannot_move_person_out_of_client_context(sessionmaker):
    """Перенос сотрудника наружу контекста — тот же увод данных, только правкой."""

    async with sessionmaker() as session:
        tid, ours, _ = await _two_clients(session)

        with pytest.raises(HTTPException) as exc:
            await persons_routes.update_person_endpoint(
                person_id=ours.id,
                payload=PersonUpdate(company_id="co-b"),
                tenant=_tenant(tid),
                session=session,
                access=SimpleNamespace(),
                scope=_scope(),
                correlation_id="c1",
            )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_is_forbidden_in_client_context(sessionmaker):
    """Доп. №3 разд. 63.2: удаление данных запрещено даже в контексте клиента."""

    async with sessionmaker() as session:
        tid, ours, _ = await _two_clients(session)

        with pytest.raises(HTTPException) as exc:
            await persons_routes.delete_person_endpoint(
                person_id=ours.id,
                tenant=_tenant(tid),
                session=session,
                access=SimpleNamespace(),
                scope=_scope(),
                correlation_id="c1",
            )

    assert exc.value.status_code == 403
    assert "Выйдите из контекста" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_medical_exams_are_filtered_by_client(sessionmaker):
    async with sessionmaker() as session:
        tid, ours, theirs = await _two_clients(session)
        await _exam(session, tid, person_id=ours.id)
        await _exam(session, tid, person_id=theirs.id)

        page = await exams_routes.list_medical_exams(
            request=_request(),
            response=_response(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=_scope(),
            person_id=None,
            status_filter=None,
            exam_kind=None,
            fitness=None,
            limit=50,
            offset=0,
        )

    assert page.total == 1
    assert {item.person_id for item in page.items} == {ours.id}


@pytest.mark.asyncio
async def test_medical_exams_are_empty_when_data_lives_elsewhere(sessionmaker):
    async with sessionmaker() as session:
        tid, ours, theirs = await _two_clients(session)
        await _exam(session, tid, person_id=ours.id)
        await _exam(session, tid, person_id=theirs.id)

        page = await exams_routes.list_medical_exams(
            request=_request(),
            response=_response(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=_scope(None, reason="Данные ведутся в отдельном контуре"),
            person_id=None,
            status_filter=None,
            exam_kind=None,
            fitness=None,
            limit=50,
            offset=0,
        )

    assert page.total == 0
    assert page.items == []


async def _allow_billing(self, tenant, action):  # noqa: ANN001 - тестовая заглушка
    return None


# ── срез-11: СИЗ, обучение, документы ──────────────────────────────────────


async def _ppe_issue(session, tid, *, person_id):
    from app.models.ppe import PPEIssue, PPEItem

    item = PPEItem(tenant_id=tid, name=f"Каска {person_id[:8]}", category="head")
    session.add(item)
    await session.flush()
    row = PPEIssue(
        tenant_id=tid,
        person_id=person_id,
        item_id=item.id,
        item_name="Каска",
        quantity=1,
        issued_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


async def _enrollment(session, tid, *, person_id):
    from app.models.training import TrainingEnrollment, TrainingProgram

    program = TrainingProgram(
        tenant_id=tid,
        code=f"OT-{person_id[:6]}",
        title="Охрана труда",
        category="ot",
        kind="course",
    )
    session.add(program)
    await session.flush()
    row = TrainingEnrollment(
        tenant_id=tid,
        person_id=person_id,
        training_program_id=program.id,
        assignment_source="manual",
        assigned_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        status="assigned",
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_ppe_issues_are_filtered_by_client(sessionmaker):
    from app.api.routes import ppe as ppe_routes

    async with sessionmaker() as session:
        tid, ours, theirs = await _two_clients(session)
        await _ppe_issue(session, tid, person_id=ours.id)
        await _ppe_issue(session, tid, person_id=theirs.id)

        page = await ppe_routes.list_issues(
            request=_request(),
            response=_response(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=_scope(),
            person_id=None,
            active_only=False,
            limit=50,
            offset=0,
        )

    # Итог считается по той же выборке: «всего 2» под списком из одной строки
    # читается как потеря данных.
    assert page.total == 1
    assert len(page.items) == 1


@pytest.mark.asyncio
async def test_training_enrollments_are_filtered_by_client(sessionmaker):
    from app.api.routes import training_next as training_routes

    async with sessionmaker() as session:
        tid, ours, theirs = await _two_clients(session)
        await _enrollment(session, tid, person_id=ours.id)
        await _enrollment(session, tid, person_id=theirs.id)

        out = await training_routes.list_enrollments(
            scope=_scope(),
            tenant=_tenant(tid),
            session=session,
            person_id=None,
            status_f=None,
        )

    assert out["total"] == 1
    assert out["items"][0].person_id == ours.id


@pytest.mark.asyncio
async def test_ppe_and_training_are_empty_when_data_lives_elsewhere(sessionmaker):
    from app.api.routes import ppe as ppe_routes
    from app.api.routes import training_next as training_routes

    async with sessionmaker() as session:
        tid, ours, theirs = await _two_clients(session)
        await _ppe_issue(session, tid, person_id=ours.id)
        await _enrollment(session, tid, person_id=theirs.id)
        elsewhere = _scope(None, reason="Данные ведутся в отдельном контуре")

        page = await ppe_routes.list_issues(
            request=_request(),
            response=_response(),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            scope=elsewhere,
            person_id=None,
            active_only=False,
            limit=50,
            offset=0,
        )
        out = await training_routes.list_enrollments(
            scope=elsewhere,
            tenant=_tenant(tid),
            session=session,
            person_id=None,
            status_f=None,
        )

    assert page.total == 0 and page.items == []
    assert out["total"] == 0


@pytest.mark.asyncio
async def test_foreign_ppe_issue_is_not_found(sessionmaker):
    from app.api.routes import ppe as ppe_routes

    async with sessionmaker() as session:
        tid, _, theirs = await _two_clients(session)
        issue = await _ppe_issue(session, tid, person_id=theirs.id)

        with pytest.raises(HTTPException) as exc:
            await ppe_routes.get_issue(
                issue_id=issue.id,
                tenant=_tenant(tid),
                session=session,
                access=SimpleNamespace(),
                scope=_scope(),
                correlation_id="c1",
            )

    assert exc.value.status_code == 404


def test_registry_now_names_five_sections() -> None:
    """Индикатор берёт названия отсюда — обещать больше сделанного нельзя."""

    from app.domains.managed_clients.scope import scoped_section_titles

    assert scoped_section_titles() == ["Люди", "Медосмотры", "СИЗ", "Обучение", "Документы"]


@pytest.mark.asyncio
async def test_documents_are_filtered_by_client(sessionmaker, data_factory):
    """У документа своя организация, поэтому фильтр прямой."""

    from uuid import uuid4

    from app.api.routes.documents import read as documents_read
    from app.models.document import DocumentStatus

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant, email=f"{uuid4()}@example.com", session=session
        )
        template = await data_factory.create_template(
            tenant=tenant, name=f"T {uuid4()}"[:36], session=session
        )
        ours_co = await data_factory.create_company(
            tenant=tenant, name=f"Наш {uuid4()}"[:36], session=session
        )
        theirs_co = await data_factory.create_company(
            tenant=tenant, name=f"Чужой {uuid4()}"[:36], session=session
        )
        for company in (ours_co, theirs_co):
            await data_factory.create_document(
                tenant=tenant,
                company=company,
                person=None,
                template=template,
                creator=user,
                status=DocumentStatus.DRAFT,
                version_payload={"v": 1},
                version_file_key=f"documents/{uuid4()}.pdf",
                session=session,
                storage_key=f"documents/{uuid4()}.pdf",
            )

        access = SimpleNamespace(
            ensure_tenant_access=lambda *a, **k: None,
            ensure_abac=lambda *a, **k: None,
            claims={},
            company_id=None,
        )
        scope = ClientDataScope(
            client_id="mc1", client_name="ООО Ромашка", company_id=str(ours_co.id)
        )
        out = await documents_read.list_documents(
            request=_request(),
            response=_response(),
            scope=scope,
            tenant=SimpleNamespace(id=tenant.id, slug=tenant.slug, code=tenant.slug),
            session=session,
            access=access,
            search=None,
            status_value=None,
            company_id=None,
            template_id=None,
            created_by=None,
            created_from=None,
            created_to=None,
            type_value=None,
            page=1,
            page_size=10,
        )

    assert out.pagination.total == 1
    assert len(out.items) == 1


@pytest.mark.asyncio
async def test_company_filter_cannot_widen_the_client_scope(sessionmaker, data_factory):
    """?company_id=<чужая организация> не должен обходить сужение."""

    from uuid import uuid4

    from app.api.routes.documents import read as documents_read
    from app.models.document import DocumentStatus

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant, email=f"{uuid4()}@example.com", session=session
        )
        template = await data_factory.create_template(
            tenant=tenant, name=f"T {uuid4()}"[:36], session=session
        )
        ours_co = await data_factory.create_company(
            tenant=tenant, name=f"Наш {uuid4()}"[:36], session=session
        )
        theirs_co = await data_factory.create_company(
            tenant=tenant, name=f"Чужой {uuid4()}"[:36], session=session
        )
        await data_factory.create_document(
            tenant=tenant,
            company=theirs_co,
            person=None,
            template=template,
            creator=user,
            status=DocumentStatus.DRAFT,
            version_payload={"v": 1},
            version_file_key=f"documents/{uuid4()}.pdf",
            session=session,
            storage_key=f"documents/{uuid4()}.pdf",
        )

        access = SimpleNamespace(
            ensure_tenant_access=lambda *a, **k: None,
            ensure_abac=lambda *a, **k: None,
            claims={},
            company_id=None,
        )
        out = await documents_read.list_documents(
            request=_request(),
            response=_response(),
            scope=ClientDataScope(
                client_id="mc1", client_name="ООО Ромашка", company_id=str(ours_co.id)
            ),
            tenant=SimpleNamespace(id=tenant.id, slug=tenant.slug, code=tenant.slug),
            session=session,
            access=access,
            search=None,
            status_value=None,
            company_id=str(theirs_co.id),
            template_id=None,
            created_by=None,
            created_from=None,
            created_to=None,
            type_value=None,
            page=1,
            page_size=10,
        )

    assert out.pagination.total == 0
    assert out.items == []
