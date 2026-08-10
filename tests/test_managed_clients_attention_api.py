"""BIZ-49 срез-2 — сбор cross-client внимания и эндпоинт (разд. 49.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.attention import AggregationStatus, Severity, SignalKind
from app.domains.managed_clients.attention_service import collect_portfolio_attention
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.master_data import Person
from app.models.medical import MedicalExam
from app.models.ppe import PPEIssue
from app.models.training import TrainingEnrollment

_TODAY = date(2026, 8, 4)
_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))


def _med(*, person_id, valid_until, tenant_id=_TENANT) -> MedicalExam:
    """Медосмотр с обязательными полями модели (exam_type/exam_date NOT NULL)."""
    return MedicalExam(
        tenant_id=tenant_id,
        person_id=person_id,
        exam_type="periodic",
        exam_date=valid_until - timedelta(days=365),
        valid_until=valid_until,
    )


def _enrollment(*, person_id, due_at, status="assigned") -> TrainingEnrollment:
    """Назначение обучения (training_program_id NOT NULL — FK не проверяется в SQLite-тестах)."""
    return TrainingEnrollment(
        tenant_id=_TENANT,
        person_id=person_id,
        training_program_id="prog-1",
        status=status,
        due_at=due_at,
    )


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


async def _person(session, *, pid, company_id, email="a@b.c", phone="+7"):
    row = Person(
        id=pid,
        tenant_id=_TENANT,
        company_id=company_id,
        first_name="И",
        last_name="И",
        email=email,
        phone=phone,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_signals_are_attributed_to_the_right_client(sessionmaker):
    """Сотрудники разных клиентов не должны смешиваться в одну кучу."""
    async with sessionmaker() as session:
        a = await _client(session, name="Альфа", company_id="comp-a")
        b = await _client(session, name="Бета", company_id="comp-b")
        await _person(session, pid="p-a1", company_id="comp-a")
        await _person(session, pid="p-b1", company_id="comp-b")
        # просроченный медосмотр только у клиента А
        session.add(_med(person_id="p-a1", valid_until=_TODAY - timedelta(days=1)))
        # просроченное обучение только у клиента Б
        session.add(_enrollment(person_id="p-b1", due_at=_NOW - timedelta(days=2)))
        await session.commit()

        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    by_id = {r.client_id: r for r in rows}
    assert [s.kind for s in by_id[a.id].signals] == [SignalKind.MEDICAL_OVERDUE]
    assert [s.kind for s in by_id[b.id].signals] == [SignalKind.TRAINING_OVERDUE]


@pytest.mark.asyncio
async def test_worst_client_is_first(sessionmaker):
    async with sessionmaker() as session:
        quiet = await _client(session, name="Тихий", company_id="comp-q")
        burning = await _client(session, name="Горит", company_id="comp-f")
        await _person(session, pid="p-f1", company_id="comp-f")
        session.add(_med(person_id="p-f1", valid_until=_TODAY - timedelta(days=5)))
        await session.commit()

        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert rows[0].client_id == burning.id
    assert rows[-1].client_id == quiet.id


@pytest.mark.asyncio
async def test_returned_ppe_is_not_overdue(sessionmaker):
    """Возвращённый СИЗ уже не у человека — считать его просрочкой нельзя."""
    async with sessionmaker() as session:
        c = await _client(session, name="Клиент", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p1",
                item_name="Каска",
                expires_at=_NOW - timedelta(days=10),
                returned_at=_NOW - timedelta(days=1),
            )
        )
        session.add(
            PPEIssue(
                tenant_id=_TENANT,
                person_id="p1",
                item_name="Перчатки",
                expires_at=_NOW - timedelta(days=3),
            )
        )
        await session.commit()

        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    signals = {s.kind: s.count for s in rows[0].signals if rows[0].client_id == c.id}
    assert signals[SignalKind.PPE_OVERDUE] == 1  # только невозвращённый


@pytest.mark.asyncio
async def test_dedicated_client_is_not_aggregated_not_zero(sessionmaker):
    async with sessionmaker() as session:
        await _client(
            session,
            name="Свой контур",
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="client-a",
        )
        await session.commit()
        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert rows[0].aggregation is AggregationStatus.NOT_AGGREGATED
    assert rows[0].total is None
    assert rows[0].reason


@pytest.mark.asyncio
async def test_dedicated_client_still_shows_contract_signal(sessionmaker):
    """Договор ведёт САМ аутсорсер — этот сигнал виден и без доступа к данным."""
    async with sessionmaker() as session:
        await _client(
            session,
            name="Свой контур",
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="client-a",
            contract_ends_at=_TODAY + timedelta(days=3),
        )
        await session.commit()
        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert [s.kind for s in rows[0].signals] == [SignalKind.CONTRACT_EXPIRING]
    assert rows[0].total is None  # остальное всё равно не собрано


@pytest.mark.asyncio
async def test_other_tenant_data_is_invisible(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Наш", company_id="comp-a")
        await _person(session, pid="p1", company_id="comp-a")
        # просрочка чужого арендатора по тому же company_id
        session.add(
            _med(person_id="p1", valid_until=_TODAY - timedelta(days=1), tenant_id="tenant-other")
        )
        await session.commit()
        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert rows[0].signals == []


@pytest.mark.asyncio
async def test_soft_deleted_person_does_not_signal(sessionmaker):
    async with sessionmaker() as session:
        await _client(session, name="Клиент", company_id="comp-a")
        p = await _person(session, pid="p1", company_id="comp-a")
        p.deleted_at = _NOW
        session.add(_med(person_id="p1", valid_until=_TODAY - timedelta(days=1)))
        await session.commit()
        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert rows[0].signals == []


@pytest.mark.asyncio
async def test_empty_portfolio_returns_nothing(sessionmaker):
    async with sessionmaker() as session:
        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    assert rows == []


# --- эндпоинт ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_endpoint_summary_and_order(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "_today", lambda: _TODAY)
    async with sessionmaker() as session:
        await _client(session, name="Тихий", company_id="comp-q")
        await _client(session, name="Горит", company_id="comp-f")
        await _client(
            session,
            name="Свой контур",
            mode=ManagedClientMode.DEDICATED,
            dedicated_tenant_slug="client-a",
        )
        await _person(session, pid="p-f1", company_id="comp-f", email=None)
        session.add(_med(person_id="p-f1", valid_until=_TODAY - timedelta(days=5)))
        await session.commit()

        out = await routes.cross_client_attention(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert out.summary.clients_total == 3
    assert out.summary.clients_not_aggregated == 1
    assert out.summary.critical_clients == 1
    assert out.items[0].client_name == "Горит"
    assert out.items[0].severity is Severity.CRITICAL
    # «не смотрели» выше «всё чисто»
    assert [i.client_name for i in out.items[1:]] == ["Свой контур", "Тихий"]


@pytest.mark.asyncio
async def test_endpoint_etag_304(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "_today", lambda: _TODAY)
    async with sessionmaker() as session:
        await _client(session, name="Клиент", company_id="comp-a")
        await session.commit()
        resp = Response()
        await routes.cross_client_attention(
            request=SimpleNamespace(headers={}),
            response=resp,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        etag = resp.headers["etag"]
        again = await routes.cross_client_attention(
            request=SimpleNamespace(headers={"if-none-match": etag}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert isinstance(again, Response) and again.status_code == 304


@pytest.mark.asyncio
async def test_endpoint_respects_feature_flag(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.cross_client_attention(
                request=SimpleNamespace(headers={}),
                response=Response(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
    assert exc.value.status_code == 404
