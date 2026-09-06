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
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.fire_safety import FireDrill, FireSafetyDocument, FireSafetyEquipment
from app.models.managed_clients import ManagedClient
from app.models.master_data import EmploymentStatus, Person, Site
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
async def test_fire_safety_overdue_is_one_signal_per_client_from_its_sites_and_people(sessionmaker):
    """BIZ-54-57 срез-87 (разд. 54.1): просрочки ПБ — сигнал портфеля.

    Слагаемые те же, что у светофора клиента (срез-86): перезарядка и поверка
    средств на площадках клиента, тренировки и документы этих площадок,
    противопожарные инструктажи его людей. Чужая площадка, средство без
    площадки, перекрытый более новым инструктаж и уволенный — не считаются.
    """

    async with sessionmaker() as session:
        a = await _client(session, name="Альфа", company_id="comp-a")
        b = await _client(session, name="Бета", company_id="comp-b")
        await _person(session, pid="p-a1", company_id="comp-a")
        await _person(session, pid="p-b1", company_id="comp-b")
        fired = await _person(session, pid="p-a9", company_id="comp-a")
        fired.employment_status = EmploymentStatus.TERMINATED
        own = Site(tenant_id=_TENANT, company_id="comp-a", name="Склад")
        other = Site(tenant_id=_TENANT, company_id="comp-b", name="Чужой цех")
        journal = BriefingJournal(
            tenant_id=_TENANT, code="J-FIRE", title="Журнал ПБ", journal_type="fire"
        )
        session.add_all([own, other, journal])
        await session.flush()

        def _unit(site_id, label, *, recharge=None, inspection=None, status="active"):
            return FireSafetyEquipment(
                tenant_id=_TENANT,
                site_id=site_id,
                kind="extinguisher",
                label=label,
                status=status,
                recharge_due=None if recharge is None else _TODAY + timedelta(days=recharge),
                inspection_due=None if inspection is None else _TODAY + timedelta(days=inspection),
            )

        def _briefing(person_id, kind, days):
            return BriefingEntry(
                tenant_id=_TENANT,
                briefing_journal_id=journal.id,
                person_id=person_id,
                briefing_type=kind,
                briefing_date=_TODAY - timedelta(days=400),
                valid_until=_NOW + timedelta(days=days),
                status="completed",
            )

        session.add_all(
            [
                # Альфа: перезарядка И поверка одного средства просрочены — два слагаемых
                _unit(own.id, "ОП-4 №1", recharge=-3, inspection=-1),
                _unit(own.id, "ОП-4 №2", recharge=200),
                # списанное средство и средство без площадки — не считаются
                _unit(own.id, "ОП-4 №3", recharge=-30, status="written_off"),
                _unit(None, "ОП-4 №4", recharge=-30),
                # тренировка не проведена к дате и документ без пересмотра
                FireDrill(
                    tenant_id=_TENANT,
                    site_id=own.id,
                    kind="evacuation",
                    title="Эвакуация",
                    planned_on=_TODAY - timedelta(days=2),
                ),
                FireDrill(
                    tenant_id=_TENANT,
                    site_id=own.id,
                    kind="evacuation",
                    title="Проведена",
                    planned_on=_TODAY - timedelta(days=9),
                    held_on=_TODAY - timedelta(days=9),
                ),
                FireSafetyDocument(
                    tenant_id=_TENANT,
                    site_id=own.id,
                    kind="instruction",
                    title="Инструкция",
                    review_due=_TODAY - timedelta(days=1),
                ),
                # ПТМ Альфы истёк; повторный — старый перекрыт новым действующим
                _briefing("p-a1", "fire_ptm", -35),
                _briefing("p-a1", "fire_repeat", -50),
                _briefing("p-a1", "fire_repeat", 100),
                # уволенный — не в счёт
                _briefing("p-a9", "fire_ptm", -35),
                # Бета: только чужая площадка с просрочкой и действующий ПТМ
                _unit(other.id, "ОП-4 №5", recharge=-30),
                _briefing("p-b1", "fire_ptm", 100),
            ]
        )
        await session.commit()

        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    by_id = {r.client_id: r for r in rows}
    fire_a = [s for s in by_id[a.id].signals if s.kind is SignalKind.FIRE_SAFETY_OVERDUE]
    assert len(fire_a) == 1, "все слагаемые ПБ — один сигнал, а не пять"
    # перезарядка 1 + поверка 1 + тренировка 1 + документ 1 + ПТМ 1
    assert fire_a[0].count == 5
    assert fire_a[0].severity is Severity.HIGH
    fire_b = [s for s in by_id[b.id].signals if s.kind is SignalKind.FIRE_SAFETY_OVERDUE]
    assert fire_b[0].count == 1, "средство чужой площадки — просрочка её клиента"


@pytest.mark.asyncio
async def test_expired_driver_license_is_a_critical_signal_of_admitted_drivers_only(sessionmaker):
    """BIZ-54-57 срез-88 (разд. 54.1): истёкшие удостоверения — сигнал портфеля.

    Правило одно со светофором клиента и календарём: только допущенные к
    управлению; пустая дата — «сведений нет», не просрочка; отстранённый,
    уволенный и чужой водитель — не считаются.
    """

    async with sessionmaker() as session:
        a = await _client(session, name="Альфа", company_id="comp-a")
        b = await _client(session, name="Бета", company_id="comp-b")
        for pid in ("p-a1", "p-a2", "p-a3", "p-a4", "p-a5"):
            await _person(session, pid=pid, company_id="comp-a")
        fired = await _person(session, pid="p-a9", company_id="comp-a")
        fired.employment_status = EmploymentStatus.TERMINATED
        await _person(session, pid="p-b1", company_id="comp-b")

        def _driver(person_id, number, *, days=None, status="admitted"):
            return Driver(
                tenant_id=_TENANT,
                person_id=person_id,
                license_number=number,
                license_due=None if days is None else _TODAY + timedelta(days=days),
                status=status,
            )

        session.add_all(
            [
                # Альфа: два истёкших у допущенных
                _driver("p-a1", "77 АА 000001", days=-1),
                _driver("p-a2", "77 АА 000002", days=-400),
                # действующее, без даты, отстранённый и уволенный — нет
                _driver("p-a3", "77 АА 000003", days=10),
                _driver("p-a4", "77 АА 000004"),
                _driver("p-a5", "77 АА 000005", days=-5, status="suspended"),
                _driver("p-a9", "77 АА 000009", days=-5),
                # Бета: чужое истёкшее — её сигнал, не Альфы
                _driver("p-b1", "77 АА 000010", days=-3),
            ]
        )
        await session.commit()

        rows = await collect_portfolio_attention(
            session, tenant_id=_TENANT, today=_TODAY, now=_NOW, horizon_days=30
        )
    by_id = {r.client_id: r for r in rows}
    sig_a = [s for s in by_id[a.id].signals if s.kind is SignalKind.DRIVER_LICENSE_EXPIRED]
    assert len(sig_a) == 1 and sig_a[0].count == 2
    assert sig_a[0].severity is Severity.CRITICAL
    assert by_id[a.id].severity is Severity.CRITICAL, "водитель без прав — как без медосмотра"
    sig_b = [s for s in by_id[b.id].signals if s.kind is SignalKind.DRIVER_LICENSE_EXPIRED]
    assert sig_b[0].count == 1
    assert rows[0].client_id == a.id, "два истёкших выше одного при равном весе"


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
async def test_endpoint_respects_feature_flag():
    # BIZ-61 срез-6: гейт больше не вызывается в теле каждого эндпоинта — он
    # роутерная зависимость и стоит на КАЖДОМ роуте по построению (забыть
    # нельзя). Прямой вызов функции эндпоинта гейт не дёргает; исходы гейта
    # (404 «не выдавался» / read-only «был выдан») доказаны живым клиентом в
    # tests/test_biz61_module_readonly.py и юнитах самого гейта.
    deps = [d.dependency for d in routes.router.dependencies]
    assert routes._require_enabled in deps
