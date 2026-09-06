"""BIZ-49 срез-4 — сбор дедлайнов портфеля и эндпоинт календаря (разд. 49.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.attention import SignalKind
from app.domains.managed_clients.attention_service import collect_portfolio_attention
from app.domains.managed_clients.calendar import CalendarFilters, DeadlineKind
from app.domains.managed_clients.calendar_service import collect_portfolio_deadlines
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.master_data import EmploymentStatus, Person
from app.models.medical import MedicalExam
from app.models.ppe import PPEIssue
from app.models.road_safety import Driver
from app.models.training import TrainingEnrollment

_TODAY = date(2026, 8, 4)
_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(routes, "_today", lambda: _TODAY)


def _at(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)


async def _client(session, *, name, company_id=None, mode=ManagedClientMode.LIGHTWEIGHT, **over):
    row = ManagedClient(
        tenant_id=_TENANT,
        name=name,
        mode=mode,
        company_id=company_id,
        contract_status=over.pop("contract_status", ContractStatus.ACTIVE),
        **over,
    )
    session.add(row)
    await session.flush()
    return row


async def _person(session, *, pid, company_id, last="Иванов", first="Иван", **over):
    row = Person(
        id=pid,
        tenant_id=_TENANT,
        company_id=company_id,
        first_name=first,
        last_name=last,
        email="a@b.c",
        phone="+7",
        **over,
    )
    session.add(row)
    await session.flush()
    return row


def _driver(person_id, number, *, days=None, status="admitted") -> Driver:
    return Driver(
        tenant_id=_TENANT,
        person_id=person_id,
        license_number=number,
        license_due=None if days is None else _TODAY + timedelta(days=days),
        status=status,
    )


def _med(*, person_id, valid_until) -> MedicalExam:
    return MedicalExam(
        tenant_id=_TENANT,
        person_id=person_id,
        exam_type="periodic",
        exam_date=valid_until - timedelta(days=365),
        valid_until=valid_until,
    )


@pytest.mark.asyncio
async def test_collects_all_deadline_kinds(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(
            session,
            name="Ромашка",
            company_id="comp-a",
            contract_no="Д-1",
            contract_ends_at=_TODAY + timedelta(days=10),
        )
        await _person(session, pid="p1", company_id="comp-a")
        session.add(_med(person_id="p1", valid_until=_TODAY + timedelta(days=3)))
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p1",
                item_name="Каска",
                expires_at=_at(_TODAY + timedelta(days=5)),
            )
        )
        session.add(
            TrainingEnrollment(
                tenant_id=_TENANT,
                person_id="p1",
                training_program_id="prog-1",
                status="assigned",
                due_at=_at(_TODAY + timedelta(days=7)),
            )
        )
        session.add(_driver("p1", "77 АА 000001", days=9))
        await session.commit()

        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    kinds = [e.kind for e in events]
    assert set(kinds) == {
        DeadlineKind.MEDICAL,
        DeadlineKind.PPE,
        DeadlineKind.TRAINING,
        DeadlineKind.CONTRACT,
        DeadlineKind.DRIVER_LICENSE,
    }
    assert all(e.client_name == "Ромашка" for e in events)
    assert all(e.client_id == c.id for e in events)


@pytest.mark.asyncio
async def test_overdue_comes_first_and_stays_in_the_list(sessionmaker):
    """Просроченный дедлайн — самое срочное; он не «в прошлом, не показываем»."""
    async with sessionmaker() as session:
        await _client(session, name="Ромашка", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        session.add(_med(person_id="p1", valid_until=_TODAY - timedelta(days=6)))
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p1",
                item_name="Каска",
                expires_at=_at(_TODAY + timedelta(days=2)),
            )
        )
        await session.commit()

        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert events[0].overdue is True
    assert events[0].kind is DeadlineKind.MEDICAL
    assert events[0].days_left == -6


@pytest.mark.asyncio
async def test_horizon_cuts_far_future_but_not_overdue(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Ромашка", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        session.add(_med(person_id="p1", valid_until=_TODAY + timedelta(days=100)))
        session.add(_med(person_id="p1", valid_until=_TODAY - timedelta(days=2)))
        await session.commit()

        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=7, now=_NOW
        )
    assert [e.days_left for e in events] == [-2]


@pytest.mark.asyncio
async def test_dedicated_client_shows_only_contract(sessionmaker):
    """Сотрудники клиента со своим контуром в другом арендаторе — их не видно."""
    async with sessionmaker() as session:
        await _client(
            session,
            name="Свой контур",
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="client-a",
            contract_no="Д-9",
            contract_ends_at=_TODAY + timedelta(days=4),
        )
        await session.commit()
        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert [e.kind for e in events] == [DeadlineKind.CONTRACT]
    assert events[0].subject == "Д-9"


@pytest.mark.asyncio
async def test_returned_ppe_has_no_deadline(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Ромашка", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p1",
                item_name="Каска",
                expires_at=_at(_TODAY + timedelta(days=2)),
                returned_at=_NOW,
            )
        )
        await session.commit()
        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert events == []


@pytest.mark.asyncio
async def test_terminated_person_has_no_deadlines(sessionmaker):
    """Уволенный — не дедлайн, а история: одно правило со сводкой внимания (срез-90).

    До среза календарь брал людей по ``deleted_at`` и показывал «просрочен
    медосмотр» у уволенного, хотя сводка внимания (срез-89) и светофор того же
    клиента про него молчат; нагрузка специалиста складывала обе цифры на одном
    экране.
    """

    async with sessionmaker() as session:
        await _client(session, name="Ромашка", company_id="comp-a")
        await _person(
            session,
            pid="p-gone",
            company_id="comp-a",
            last="Ушедший",
            employment_status=EmploymentStatus.TERMINATED,
        )
        session.add(_med(person_id="p-gone", valid_until=_TODAY - timedelta(days=5)))
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p-gone",
                item_name="Каска",
                expires_at=_at(_TODAY + timedelta(days=2)),
            )
        )
        session.add(
            TrainingEnrollment(
                tenant_id=_TENANT,
                person_id="p-gone",
                training_program_id="prog-1",
                status="assigned",
                due_at=_at(_TODAY - timedelta(days=1)),
            )
        )
        await _person(session, pid="p-here", company_id="comp-a", last="Работающий")
        session.add(_med(person_id="p-here", valid_until=_TODAY + timedelta(days=3)))
        await session.commit()

        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert [(e.kind, e.subject) for e in events] == [(DeadlineKind.MEDICAL, "Работающий Иван")]


@pytest.mark.asyncio
async def test_driver_license_deadlines_of_admitted_drivers_only(sessionmaker):
    """Удостоверения водителей в календаре — одним правилом со сводкой внимания (срез-91).

    Сводка поднимала сигнал ``driver_license_expired`` (срез-88), а календарь
    даты удостоверений не знал: специалист видел «горит», но не видел когда.
    Считаются только допущенные с датой, не уволенные; истёкшее — просрочка и
    первым; просроченных в календаре столько же, сколько в сигнале.
    """

    async with sessionmaker() as session:
        await _client(session, name="Альфа", company_id="comp-a")
        await _client(session, name="Бета", company_id="comp-b")
        for pid, last, over in (
            ("p-a1", "Истёкший", {}),
            ("p-a2", "Скорый", {}),
            ("p-a3", "Далёкий", {}),
            ("p-a4", "Бессрочный", {}),
            ("p-a5", "Отстранённый", {}),
            ("p-a9", "Уволенный", {"employment_status": EmploymentStatus.TERMINATED}),
            ("p-b1", "Соседский", {}),
        ):
            await _person(
                session,
                pid=pid,
                company_id="comp-b" if pid == "p-b1" else "comp-a",
                last=last,
                **over,
            )
        session.add_all(
            [
                _driver("p-a1", "77 АА 000001", days=-3),
                _driver("p-a2", "77 АА 000002", days=5),
                _driver("p-a3", "77 АА 000003", days=200),
                _driver("p-a4", "77 АА 000004"),
                _driver("p-a5", "77 АА 000005", days=1, status="suspended"),
                _driver("p-a9", "77 АА 000009", days=-1),
                _driver("p-b1", "77 АА 000011", days=2),
            ]
        )
        await session.commit()

        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
        attention = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )

    assert [(e.kind, e.client_name, e.subject, e.overdue) for e in events] == [
        (DeadlineKind.DRIVER_LICENSE, "Альфа", "Истёкший Иван", True),
        (DeadlineKind.DRIVER_LICENSE, "Бета", "Соседский Иван", False),
        (DeadlineKind.DRIVER_LICENSE, "Альфа", "Скорый Иван", False),
    ]
    assert all(e.title == "Удостоверение водителя" for e in events)
    # паритет со сводкой внимания: просроченных в календаре столько же, сколько в сигнале
    alpha = next(row for row in attention if row.client_name == "Альфа")
    signal = next(s for s in alpha.signals if s.kind is SignalKind.DRIVER_LICENSE_EXPIRED)
    overdue_in_calendar = sum(
        1
        for e in events
        if e.kind is DeadlineKind.DRIVER_LICENSE and e.overdue and e.client_name == "Альфа"
    )
    assert signal.count == overdue_in_calendar == 1


@pytest.mark.asyncio
async def test_filters_by_client_and_kind(sessionmaker):
    async with sessionmaker() as session:
        a = await _client(session, name="Альфа", company_id="comp-a")
        await _client(session, name="Бета", company_id="comp-b")
        await _person(session, pid="p-a", company_id="comp-a")
        await _person(session, pid="p-b", company_id="comp-b")
        session.add(_med(person_id="p-a", valid_until=_TODAY + timedelta(days=2)))
        session.add(_med(person_id="p-b", valid_until=_TODAY + timedelta(days=2)))
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p-a",
                item_name="Каска",
                expires_at=_at(_TODAY + timedelta(days=3)),
            )
        )
        await session.commit()

        only_a = await collect_portfolio_deadlines(
            session,
            tenant_id=_TENANT,
            today=_TODAY,
            horizon_days=30,
            filters=CalendarFilters(client_id=a.id),
            now=_NOW,
        )
        only_med = await collect_portfolio_deadlines(
            session,
            tenant_id=_TENANT,
            today=_TODAY,
            horizon_days=30,
            filters=CalendarFilters(kinds={DeadlineKind.MEDICAL}),
            now=_NOW,
        )
    assert {e.client_id for e in only_a} == {a.id}
    assert {e.kind for e in only_med} == {DeadlineKind.MEDICAL}
    assert len(only_med) == 2


@pytest.mark.asyncio
async def test_filter_by_responsible_specialist(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Альфа", company_id="comp-a", responsible_person_id="spec-1")
        await _client(session, name="Бета", company_id="comp-b", responsible_person_id="spec-2")
        await _person(session, pid="p-a", company_id="comp-a")
        await _person(session, pid="p-b", company_id="comp-b")
        session.add(_med(person_id="p-a", valid_until=_TODAY + timedelta(days=2)))
        session.add(_med(person_id="p-b", valid_until=_TODAY + timedelta(days=2)))
        await session.commit()

        events = await collect_portfolio_deadlines(
            session,
            tenant_id=_TENANT,
            today=_TODAY,
            horizon_days=30,
            filters=CalendarFilters(responsible_person_id="spec-1"),
            now=_NOW,
        )
    assert [e.client_name for e in events] == ["Альфа"]


@pytest.mark.asyncio
async def test_other_tenant_is_invisible(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Наш", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        alien = _med(person_id="p1", valid_until=_TODAY + timedelta(days=2))
        alien.tenant_id = "tenant-other"
        session.add(alien)
        await session.commit()
        events = await collect_portfolio_deadlines(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert events == []


# --- эндпоинт ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_endpoint_groups_by_day_with_summary(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Ромашка", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        session.add(_med(person_id="p1", valid_until=_TODAY - timedelta(days=1)))
        session.add(_med(person_id="p1", valid_until=_TODAY))
        session.add(_med(person_id="p1", valid_until=_TODAY + timedelta(days=2)))
        await session.commit()

        out = await routes.cross_client_calendar(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
            client_id=None,
            responsible_person_id=None,
            kind=None,
        )
    assert out.summary.events_total == 3
    assert out.summary.overdue == 1
    assert out.summary.due_today == 1
    assert out.summary.upcoming == 1
    assert [d.overdue for d in out.days] == [True, False, False]
    assert out.horizon_days == 30


@pytest.mark.asyncio
async def test_endpoint_etag_304(sessionmaker):
    async with sessionmaker() as session:
        await _client(
            session,
            name="Ромашка",
            company_id="comp-a",
            contract_ends_at=_TODAY + timedelta(days=5),
        )
        await session.commit()
        resp = Response()
        await routes.cross_client_calendar(
            request=SimpleNamespace(headers={}),
            response=resp,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
            client_id=None,
            responsible_person_id=None,
            kind=None,
        )
        etag = resp.headers["etag"]
        again = await routes.cross_client_calendar(
            request=SimpleNamespace(headers={"if-none-match": etag}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
            client_id=None,
            responsible_person_id=None,
            kind=None,
        )
    assert isinstance(again, Response) and again.status_code == 304


@pytest.mark.asyncio
async def test_endpoint_etag_differs_per_filter(sessionmaker):
    """Кэш фильтра не должен подменять другой срез календаря."""
    async with sessionmaker() as session:
        c = await _client(
            session,
            name="Ромашка",
            company_id="comp-a",
            contract_ends_at=_TODAY + timedelta(days=5),
        )
        await session.commit()
        r1, r2 = Response(), Response()
        common = dict(
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
            responsible_person_id=None,
            kind=None,
        )
        await routes.cross_client_calendar(
            request=SimpleNamespace(headers={}), response=r1, client_id=None, **common
        )
        await routes.cross_client_calendar(
            request=SimpleNamespace(headers={}), response=r2, client_id=c.id, **common
        )
    assert r1.headers["etag"] != r2.headers["etag"]


@pytest.mark.asyncio
async def test_endpoint_respects_feature_flag():
    # BIZ-61 срез-6: гейт больше не вызывается в теле каждого эндпоинта — он
    # роутерная зависимость и стоит на КАЖДОМ роуте по построению (забыть
    # нельзя). Прямой вызов функции эндпоинта гейт не дёргает; исходы гейта
    # (404 «не выдавался» / read-only «был выдан») доказаны живым клиентом в
    # tests/test_biz61_module_readonly.py и юнитах самого гейта.
    deps = [d.dependency for d in routes.router.dependencies]
    assert routes._require_enabled in deps
