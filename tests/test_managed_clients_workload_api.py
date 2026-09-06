"""BIZ-49 срез-5 — сбор загрузки специалистов и эндпоинт (разд. 49.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.domains.managed_clients.workload import UNASSIGNED_KEY, OverloadReason
from app.domains.managed_clients.workload_service import collect_specialist_workload
from app.models.managed_clients import ManagedClient
from app.models.master_data import EmploymentStatus, Person
from app.models.medical import MedicalExam

_TODAY = date(2026, 8, 4)
_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(routes, "_today", lambda: _TODAY)


async def _client(session, *, name, company_id=None, responsible=None, **over):
    row = ManagedClient(
        tenant_id=_TENANT,
        name=name,
        mode=over.pop("mode", ManagedClientMode.LIGHTWEIGHT),
        company_id=company_id,
        responsible_person_id=responsible,
        contract_status=over.pop("contract_status", ContractStatus.ACTIVE),
        **over,
    )
    session.add(row)
    await session.flush()
    return row


async def _person(session, *, pid, company_id=None, last="Петров", first="Пётр", **over):
    row = Person(
        id=pid,
        tenant_id=_TENANT,
        company_id=company_id or "comp-x",
        first_name=first,
        last_name=last,
        email="a@b.c",
        phone="+7",
        **over,
    )
    session.add(row)
    await session.flush()
    return row


def _med(*, person_id, valid_until) -> MedicalExam:
    return MedicalExam(
        tenant_id=_TENANT,
        person_id=person_id,
        exam_type="periodic",
        exam_date=valid_until - timedelta(days=365),
        valid_until=valid_until,
    )


@pytest.mark.asyncio
async def test_counts_clients_per_specialist(sessionmaker):
    async with sessionmaker() as session:
        await _person(session, pid="spec-1", last="Иванов", first="Иван")
        await _client(session, name="А", company_id="comp-a", responsible="spec-1")
        await _client(session, name="Б", company_id="comp-b", responsible="spec-1")
        await session.commit()

        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert len(rows) == 1
    assert rows[0].person_id == "spec-1"
    assert rows[0].person_name == "Иванов Иван"
    assert rows[0].clients_total == 2


@pytest.mark.asyncio
async def test_unassigned_clients_get_their_own_row(sessionmaker):
    """Работа без ответственного видна отдельно, а не растворяется."""
    async with sessionmaker() as session:
        await _person(session, pid="spec-1")
        await _client(session, name="С ответственным", company_id="comp-a", responsible="spec-1")
        await _client(session, name="Ничей", company_id="comp-b")
        await session.commit()

        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    unassigned = [r for r in rows if r.unassigned]
    assert len(unassigned) == 1
    assert unassigned[0].clients_total == 1
    assert unassigned[0].person_id == UNASSIGNED_KEY
    # и он в самом конце, но не удалён
    assert rows[-1].unassigned is True


@pytest.mark.asyncio
async def test_signals_and_overdue_are_attributed_to_specialist(sessionmaker):
    async with sessionmaker() as session:
        await _person(session, pid="spec-1")
        await _client(session, name="Горит", company_id="comp-a", responsible="spec-1")
        await _person(session, pid="w1", company_id="comp-a", last="Сидоров")
        session.add(_med(person_id="w1", valid_until=_TODAY - timedelta(days=5)))
        await session.commit()

        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    row = rows[0]
    assert row.signals_total >= 1
    assert row.overdue_deadlines == 1
    assert row.clients_critical == 1
    assert row.overloaded is True
    assert OverloadReason.CRITICAL_CLIENT in row.overload_reasons


@pytest.mark.asyncio
async def test_terminated_person_adds_neither_signal_nor_overdue(sessionmaker):
    """Сигналы и просрочки на одной строке нагрузки считают людей одним правилом (срез-90).

    Истёкший медосмотр уволенного до среза давал ``overdue_deadlines == 1`` при
    ``signals_total == 0`` — строка специалиста противоречила сама себе.
    """

    async with sessionmaker() as session:
        await _person(session, pid="spec-1")
        await _client(session, name="Тихо", company_id="comp-a", responsible="spec-1")
        await _person(
            session,
            pid="w-gone",
            company_id="comp-a",
            last="Ушедший",
            employment_status=EmploymentStatus.TERMINATED,
        )
        session.add(_med(person_id="w-gone", valid_until=_TODAY - timedelta(days=5)))
        await session.commit()

        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    row = rows[0]
    assert (row.signals_total, row.overdue_deadlines) == (0, 0)
    assert row.clients_critical == 0
    assert row.overloaded is False


@pytest.mark.asyncio
async def test_specialist_without_person_row_still_visible(sessionmaker):
    """Ответственный удалён/из другой организации — строка не исчезает."""
    async with sessionmaker() as session:
        await _client(session, name="А", company_id="comp-a", responsible="ghost-1")
        await session.commit()
        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert rows[0].person_id == "ghost-1"
    assert rows[0].person_name == "ghost-1"


@pytest.mark.asyncio
async def test_empty_portfolio_gives_nothing(sessionmaker):
    async with sessionmaker() as session:
        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert rows == []


@pytest.mark.asyncio
async def test_other_tenant_clients_are_invisible(sessionmaker):
    async with sessionmaker() as session:
        alien = ManagedClient(
            tenant_id="tenant-other",
            name="Чужой",
            mode=ManagedClientMode.LIGHTWEIGHT,
            company_id="comp-z",
            responsible_person_id="spec-1",
            contract_status=ContractStatus.ACTIVE,
        )
        session.add(alien)
        await session.commit()
        rows = await collect_specialist_workload(
            session, tenant_id=_TENANT, today=_TODAY, horizon_days=30, now=_NOW
        )
    assert rows == []


# --- эндпоинт ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_endpoint_returns_thresholds_and_summary(sessionmaker):
    async with sessionmaker() as session:
        await _person(session, pid="spec-1", last="Иванов", first="Иван")
        await _client(session, name="А", company_id="comp-a", responsible="spec-1")
        await _client(session, name="Ничей", company_id="comp-b")
        await _person(session, pid="w1", company_id="comp-a")
        session.add(_med(person_id="w1", valid_until=_TODAY - timedelta(days=2)))
        await session.commit()

        out = await routes.specialist_workload(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
        )
    # пороги видны клиенту: иначе «перегружен» — необъяснимый вердикт
    assert out.thresholds.max_clients > 0
    assert out.summary.specialists_total == 1
    assert out.summary.clients_unassigned == 1
    assert out.summary.overloaded == 1
    top = out.items[0]
    assert top.overloaded is True
    assert top.overload_reasons and top.overload_reasons[0].text


@pytest.mark.asyncio
async def test_endpoint_etag_304(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="А", company_id="comp-a", responsible="spec-1")
        await session.commit()
        resp = Response()
        await routes.specialist_workload(
            request=SimpleNamespace(headers={}),
            response=resp,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
        )
        etag = resp.headers["etag"]
        again = await routes.specialist_workload(
            request=SimpleNamespace(headers={"if-none-match": etag}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            days=30,
        )
    assert isinstance(again, Response) and again.status_code == 304


@pytest.mark.asyncio
async def test_endpoint_respects_feature_flag():
    # BIZ-61 срез-6: гейт больше не вызывается в теле каждого эндпоинта — он
    # роутерная зависимость и стоит на КАЖДОМ роуте по построению (забыть
    # нельзя). Прямой вызов функции эндпоинта гейт не дёргает; исходы гейта
    # (404 «не выдавался» / read-only «был выдан») доказаны живым клиентом в
    # tests/test_biz61_module_readonly.py и юнитах самого гейта.
    deps = [d.dependency for d in routes.router.dependencies]
    assert routes._require_enabled in deps
