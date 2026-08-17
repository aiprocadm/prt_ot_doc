"""BIZ-51 срез-5: светофор соответствия клиента по HTTP (разд. 51.3).

Правила цвета проверены построчно в ``tests/test_client_readiness.py``;
здесь — связка целиком через живой HTTP (урок среза-6 BIZ-49). Закрепляется:

* сотрудник, которому по норме должности положен медосмотр, а записи нет
  ВОВСЕ, даёт красный с «не оформлено вовсе» — «Центр внимания» такого не
  видит в принципе;
* действующие записи дают зелёный, истекающие — жёлтый;
* дисциплины без поимённого учёта отданы с причиной, а не выкрашены;
* Dedicated-клиент — честное ``not_aggregated``, не нули;
* выключенный модуль — 404.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.medical import MedicalExam, MedicalExamKind, MedicalNorm
from app.models.models import Position, RoleEnum

BASE = "/api/v1/managed-clients"

TODAY = date.today()


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
