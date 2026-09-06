"""BIZ-51 срез-5: светофор соответствия клиента по HTTP (разд. 51.3).

Правила цвета проверены построчно в ``tests/test_client_readiness.py``;
здесь — связка целиком через живой HTTP (урок среза-6 BIZ-49). Закрепляется:

* сотрудник, которому по норме должности положен медосмотр, а записи нет
  ВОВСЕ, даёт красный с «не оформлено вовсе» — «Центр внимания» такого не
  видит в принципе;
* действующие записи дают зелёный, истекающие — жёлтый;
* дисциплины без поимённого учёта отданы с причиной, а не выкрашены;
* БДД у клиента считается тем же правилом, что у сотрудника и площадки
  (срез-64): истёкшее удостоверение водителя — красный, а не «не ведётся»;
* ПБ у клиента (срез-86) — той же формулой, что у площадки 360°: средства
  на площадках его организации и инструктажи его людей; чужие площадки,
  чужие люди и средство без площадки — не его;
* Dedicated-клиент — честное ``not_aggregated``, не нули;
* выключенный модуль — 404.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.attention import SignalKind
from app.domains.managed_clients.attention_service import collect_portfolio_attention
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.fire_safety import FireSafetyEquipment
from app.models.managed_clients import ManagedClient
from app.models.master_data import Site
from app.models.medical import MedicalExam, MedicalExamKind, MedicalNorm
from app.models.models import Position, RoleEnum
from app.models.road_safety import Driver

BASE = "/api/v1/managed-clients"

#: Пять дисциплин Доп. №1 — продаваемые модули; по умолчанию у арендатора
#: теста они НЕ выданы (BIZ-61), и светофор/отчёт их не показывают (срез-55).
DISCIPLINE_MODULES = (
    "fire_safety",
    "industrial_safety",
    "ecology",
    "civil_defense",
    "road_safety",
)

TODAY = date.today()
NOW = datetime.now(tz=timezone.utc)


@pytest.fixture(autouse=True)
def _module_on(monkeypatch: pytest.MonkeyPatch):
    from unittest.mock import AsyncMock

    from app.api import dependencies_managed_client as deps
    from app.api.routes import managed_clients as routes

    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(deps, "is_module_enabled", AsyncMock(return_value=True), raising=False)


async def _trusted():
    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


@pytest.fixture()
async def served_client(sessionmaker, data_factory):
    """Клиент-«лайт» с сотрудником на должности, у которой есть норма."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # Редакция «всё включено»: иначе в светофоре остались бы три дисциплины ядра.
        await data_factory.set_modules(session, tenant.id, DISCIPLINE_MODULES, on=True)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Слесарь")
        session.add(position)
        await session.flush()
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Иванов",
            first_name="Иван",
            position_id=position.id,
            session=session,
        )
        session.add(
            MedicalNorm(
                tenant_id=tenant.id,
                position_id=position.id,
                exam_kind=MedicalExamKind.PERIODIC,
                interval_days=365,
            )
        )
        client = ManagedClient(
            tenant_id=tenant.id,
            name="ООО АКМЕ",
            mode=ManagedClientMode.LIGHTWEIGHT,
            contract_status=ContractStatus.ACTIVE,
            company_id=company.id,
        )
        session.add(client)
        await session.commit()
        return tenant, person, client.id


async def _add_exam(tenant_id: str, person_id: str, valid_until: date) -> None:
    async with await _trusted() as session:
        session.add(
            MedicalExam(
                tenant_id=tenant_id,
                person_id=person_id,
                exam_type="периодический",
                exam_kind=MedicalExamKind.PERIODIC,
                exam_date=valid_until - timedelta(days=365),
                valid_until=valid_until,
            )
        )
        await session.commit()


async def _readiness(async_client: AsyncClient, headers, mcid: str) -> dict:
    response = await async_client.get(f"{BASE}/{mcid}/readiness", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _direction(body: dict, key: str) -> dict:
    return next(d for d in body["directions"] if d["direction"] == key)


@pytest.mark.anyio
class TestClientReadiness:
    async def test_положено_но_нет_вовсе_красный(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        assert body["aggregation"] == "aggregated"
        assert body["overall"] == "red"
        medical = _direction(body, "medical")
        assert medical["light"] == "red"
        assert medical["missing"] == 1
        assert "не оформлено вовсе" in medical["reason"]

    async def test_действующий_медосмотр_даёт_зелёный(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, person, mcid = served_client
        await _add_exam(tenant.id, person.id, TODAY + timedelta(days=200))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        medical = _direction(body, "medical")
        assert medical["light"] == "green", medical
        # СИЗ-норм нет → «эталон не задан», и итог считается по измеренному.
        assert body["overall"] == "green"

    async def test_истекающий_медосмотр_даёт_жёлтый(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, person, mcid = served_client
        await _add_exam(tenant.id, person.id, TODAY + timedelta(days=10))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        assert _direction(body, "medical")["light"] == "yellow"
        assert body["overall"] == "yellow"

    async def test_истёкший_медосмотр_это_lapsed_не_missing(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, person, mcid = served_client
        await _add_exam(tenant.id, person.id, TODAY - timedelta(days=5))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        medical = _direction(body, "medical")
        assert medical["light"] == "red"
        assert (medical["missing"], medical["lapsed"]) == (0, 1)

    async def test_дисциплины_без_учёта_названы_с_причиной(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        _, _, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        assert len(body["directions"]) == 8
        ecology = _direction(body, "ecology")
        assert ecology["light"] == "not_measured"
        assert "не ведётся" in ecology["reason"]
        assert body["not_applicable"] is None

    async def test_удостоверение_водителя_красит_бдд_клиента(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        """Срез-64: у клиента и у его сотрудника БДД одного цвета."""

        tenant, person, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)
        before = _direction(await _readiness(async_client, headers, mcid), "road_safety")
        assert before["light"] == "not_measured"
        assert "эталон" in before["reason"]

        async with await _trusted() as session:
            session.add(
                Driver(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    license_number="77 АА 000001",
                    license_due=TODAY - timedelta(days=2),
                    status="admitted",
                )
            )
            await session.commit()

        after = _direction(await _readiness(async_client, headers, mcid), "road_safety")
        assert after["light"] == "red"
        assert after["reason"] == "Истекло водительское удостоверение: 1"
        assert after["required"] == 1
        assert after["lapsed"] == 1

    async def test_сроки_пб_площадок_и_инструктажи_людей_клиента_красят_пб(
        self, async_client: AsyncClient, make_auth_headers, served_client, data_factory
    ) -> None:
        """Срез-86: ПБ клиента — та же формула, что у площадки 360° и сводки МЧС.

        Чужая организация с её площадкой и людьми, а также огнетушитель без
        площадки — не клиента: приписать их значило бы угадать.
        """

        tenant, person, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)
        before = _direction(await _readiness(async_client, headers, mcid), "fire_safety")
        assert before["light"] == "not_measured"
        assert "не ведётся" in before["reason"]

        async with await _trusted() as session:
            other_company = await data_factory.create_company(
                tenant=tenant, name="ООО Чужие", session=session
            )
            stranger = await data_factory.create_person(
                tenant=tenant, company=other_company, last_name="Чужаков", session=session
            )
            own_site = Site(tenant_id=tenant.id, company_id=person.company_id, name="Склад")
            other_site = Site(tenant_id=tenant.id, company_id=other_company.id, name="Чужой цех")
            journal = BriefingJournal(
                tenant_id=tenant.id, code="J-FIRE", title="Журнал ПБ", journal_type="fire"
            )
            session.add_all([own_site, other_site, journal])
            await session.flush()

            def _unit(site_id, label, days):
                return FireSafetyEquipment(
                    tenant_id=tenant.id,
                    site_id=site_id,
                    kind="extinguisher",
                    label=label,
                    recharge_due=TODAY + timedelta(days=days),
                )

            def _ptm(person_id, days):
                return BriefingEntry(
                    tenant_id=tenant.id,
                    briefing_journal_id=journal.id,
                    person_id=person_id,
                    briefing_type="fire_ptm",
                    briefing_date=TODAY - timedelta(days=400),
                    valid_until=NOW + timedelta(days=days),
                    status="completed",
                )

            session.add_all(
                [
                    # своя площадка: просрочка и действующий
                    _unit(own_site.id, "ОП-4 №1", -3),
                    _unit(own_site.id, "ОП-4 №2", 200),
                    # чужая площадка и без площадки — не клиента
                    _unit(other_site.id, "ОП-4 №3", -30),
                    _unit(None, "ОП-4 №4", -30),
                    # ПТМ своего человека истёк; чужого — не считается
                    _ptm(person.id, -35),
                    _ptm(stranger.id, -35),
                ]
            )
            await session.commit()

        after = _direction(await _readiness(async_client, headers, mcid), "fire_safety")
        assert after["light"] == "red"
        assert after["reason"] == (
            "Просрочено по ПБ — перезарядка средств защиты: 1, противопожарные инструктажи: 1; "
            "средств без записи о работах: 2; проведённых тренировок нет"
        )
        # два средства своей площадки + один ПТМ; просрочено — по одному
        assert (after["required"], after["lapsed"], after["expiring"]) == (3, 2, 0)

        # Срез-87: сигнал «Просрочки по ПБ» в сводке портфеля — та же формула,
        # что и «просрочено» светофора клиента; расхождение — две правды.
        async with await _trusted() as session:
            portfolio = await collect_portfolio_attention(
                session, tenant_id=tenant.id, today=TODAY, now=NOW, horizon_days=30
            )
        mine = next(r for r in portfolio if r.client_id == mcid)
        fire = next(s for s in mine.signals if s.kind is SignalKind.FIRE_SAFETY_OVERDUE)
        assert fire.count == after["lapsed"] == 2

    async def test_клиент_без_площадок_считает_только_инструктажи_людей(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        """Площадок нет — средства арендатора клиенту не приписываются, но
        истёкший ПТМ его человека — просрочка."""

        tenant, person, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)

        async with await _trusted() as session:
            journal = BriefingJournal(
                tenant_id=tenant.id, code="J-FIRE-0", title="Журнал ПБ", journal_type="fire"
            )
            session.add(journal)
            await session.flush()
            session.add_all(
                [
                    # огнетушитель арендатора без площадки — не клиента
                    FireSafetyEquipment(
                        tenant_id=tenant.id,
                        kind="extinguisher",
                        label="ОП-4 №0",
                        recharge_due=TODAY - timedelta(days=30),
                    ),
                    BriefingEntry(
                        tenant_id=tenant.id,
                        briefing_journal_id=journal.id,
                        person_id=person.id,
                        briefing_type="fire_ptm",
                        briefing_date=TODAY - timedelta(days=400),
                        valid_until=NOW - timedelta(days=35),
                        status="completed",
                    ),
                ]
            )
            await session.commit()

        row = _direction(await _readiness(async_client, headers, mcid), "fire_safety")
        assert row["light"] == "red"
        assert row["reason"] == (
            "Просрочено по ПБ — противопожарные инструктажи: 1; проведённых тренировок нет"
        )
        assert (row["required"], row["lapsed"]) == (1, 1)

    async def test_дисциплина_вне_редакции_исполнителя_скрыта_и_названа(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        served_client,
        sessionmaker,
        data_factory,
    ) -> None:
        """BIZ-54-57 срез-55, приёмка §58.3: модуль выключен — строки нет, фраза есть."""

        tenant, _, mcid = served_client
        async with sessionmaker() as session:
            await data_factory.set_modules(session, tenant.id, ("ecology",), on=False)
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, mcid)

        assert len(body["directions"]) == 7
        assert "ecology" not in {d["direction"] for d in body["directions"]}
        assert body["overall"] == "red", "итог по оставшимся: норма без экзамена"
        assert body["not_applicable"] == (
            "Вне редакции арендатора (модуль не выдан или выключен): Экология"
        )

    async def test_dedicated_клиент_честное_not_aggregated(
        self, async_client: AsyncClient, make_auth_headers, served_client, sessionmaker
    ) -> None:
        tenant, *_ = served_client
        async with sessionmaker() as session:
            row = ManagedClient(
                tenant_id=tenant.id,
                name="АО Крупный",
                mode=ManagedClientMode.DEDICATED,
                contract_status=ContractStatus.ACTIVE,
                dedicated_tenant_slug="krupny",
            )
            session.add(row)
            await session.commit()
            dedicated_id = row.id
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _readiness(async_client, headers, dedicated_id)

        assert body["aggregation"] == "not_aggregated"
        assert body["overall"] is None
        assert body["directions"] == []
        assert body["reason"]

    async def test_выключенный_модуль_отвечает_404(
        self, async_client: AsyncClient, make_auth_headers, served_client, monkeypatch
    ) -> None:
        from unittest.mock import AsyncMock

        from app.api.routes import managed_clients as routes

        _, _, mcid = served_client
        monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(f"{BASE}/{mcid}/readiness", headers=headers)

        assert response.status_code == 404, response.text
