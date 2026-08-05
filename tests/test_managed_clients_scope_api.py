"""BIZ-49 срез-9 — контекст клиента как ФИЛЬТР данных (разд. 49.3).

Проверяется главное обещание индикатора «вы работаете от имени X»: в разделах,
которые он называет, видны данные ТОЛЬКО этого клиента.
"""

from __future__ import annotations

from datetime import date
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
