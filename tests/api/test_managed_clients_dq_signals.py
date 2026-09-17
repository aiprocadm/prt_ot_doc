"""BIZ-51 срез-3: сбор просрочек Data Quality в ленту клиента (разд. 51.2).

Правила превращения проверены построчно в ``tests/test_client_dq_signals.py``;
здесь закрепляется связка целиком, через живой HTTP (урок среза-6 BIZ-49:
роут без цепочки зависимостей отвечает 401, и юнит-тесты этого не видят):

* просрочка сотрудника обслуживаемого клиента попадает в его ленту с
  источником ``data_quality`` и датой САМОГО истечения;
* повторный сбор ленту не удваивает — итог честно говорит «уже в лентах»;
* просрочка собственных сотрудников аутсорсера (компания без карточки
  клиента) в ленту не идёт и названа в итоге отдельным числом;
* продлённая и снова просроченная запись даёт НОВЫЙ сигнал;
* выключенный модуль — 404, а не тихий успех.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.client_changes import ClientChange
from app.models.managed_clients import ManagedClient
from app.models.medical import MedicalExam
from app.models.models import RoleEnum

BASE = "/api/v1/managed-clients"

EXPIRED = date.today() - timedelta(days=30)


@pytest.fixture(autouse=True)
def _module_on(monkeypatch: pytest.MonkeyPatch):
    """Модуль аутсорсера включён: сбор живёт в его кабинете."""

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
    """Клиент-«лайт» с сотрудником: компания живёт внутри арендатора."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Иванов",
            first_name="Иван",
            session=session,
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
        return tenant, company, person, client.id


async def _add_expired_exam(tenant_id: str, person_id: str, valid_until: date) -> str:
    async with await _trusted() as session:
        exam = MedicalExam(
            tenant_id=tenant_id,
            person_id=person_id,
            exam_type="периодический",
            exam_date=valid_until - timedelta(days=365),
            valid_until=valid_until,
        )
        session.add(exam)
        await session.commit()
        return exam.id


async def _collect(async_client: AsyncClient, headers) -> dict:
    response = await async_client.post(f"{BASE}/dq-signals", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _feed(tenant_id: str) -> list[ClientChange]:
    async with await _trusted() as session:
        rows = (
            await session.execute(
                select(ClientChange)
                .where(ClientChange.tenant_id == tenant_id)
                .order_by(ClientChange.created_at)
            )
        ).scalars()
        return list(rows)


@pytest.mark.anyio
class TestDataQualityFeedsTheChangeLog:
    async def test_просрочка_клиента_попадает_в_ленту(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, person, mcid = served_client
        await _add_expired_exam(tenant.id, person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)

        outcome = await _collect(async_client, headers)

        assert outcome["recorded"] == 1, outcome
        feed = await _feed(tenant.id)
        assert len(feed) == 1
        row = feed[0]
        assert row.managed_client_id == mcid
        assert row.kind.value == "deadline_approaching"
        assert row.happened_on == EXPIRED
        assert row.source == "data_quality"
        assert "медосмотр" in row.summary
        assert "Иванов" in row.summary

    async def test_запись_видна_в_ленте_клиента_по_http(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, person, mcid = served_client
        await _add_expired_exam(tenant.id, person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _collect(async_client, headers)

        response = await async_client.get(f"{BASE}/{mcid}/changes", headers=headers)

        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["source"] == "data_quality"
        assert items[0]["suggestions"], "вид «Наступает срок» обязан нести подсказки"

    async def test_повторный_сбор_не_удваивает(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, person, _ = served_client
        await _add_expired_exam(tenant.id, person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _collect(async_client, headers)

        outcome = await _collect(async_client, headers)

        assert outcome["recorded"] == 0, outcome
        assert outcome["already_in_feed"] == 1, outcome
        assert len(await _feed(tenant.id)) == 1

    async def test_свои_сотрудники_в_ленту_не_идут(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        served_client,
        data_factory,
        sessionmaker,
    ) -> None:
        """Компания без карточки клиента — не клиент: её просрочки остаются
        в отчёте качества данных и честно названы в итоге."""

        tenant, *_ = served_client
        async with sessionmaker() as session:
            own_company = await data_factory.create_company(
                tenant=tenant, name="Своя контора", session=session
            )
            own_person = await data_factory.create_person(
                tenant=tenant, company=own_company, last_name="Свой", session=session
            )
        await _add_expired_exam(tenant.id, own_person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)

        outcome = await _collect(async_client, headers)

        assert outcome["recorded"] == 0, outcome
        assert outcome["not_client_related"] == 1, outcome
        assert await _feed(tenant.id) == []

    async def test_продлённая_и_снова_просроченная_даёт_новый_сигнал(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, person, _ = served_client
        exam_id = await _add_expired_exam(tenant.id, person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _collect(async_client, headers)

        # Продлили — и срок истёк снова, уже с новой датой.
        async with await _trusted() as session:
            await session.execute(
                update(MedicalExam)
                .where(MedicalExam.id == exam_id)
                .values(valid_until=EXPIRED + timedelta(days=7))
            )
            await session.commit()
        outcome = await _collect(async_client, headers)

        assert outcome["recorded"] == 1, outcome
        assert len(await _feed(tenant.id)) == 2

    async def test_без_просрочек_итог_пустой_но_честный(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, person, _ = served_client
        await _add_expired_exam(tenant.id, person.id, date.today() + timedelta(days=90))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        outcome = await _collect(async_client, headers)

        assert outcome["found"] == 0, outcome
        assert outcome["summary"] == "Просрочек не найдено"

    async def test_слагаемые_итога_сходятся(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        served_client,
        data_factory,
        sessionmaker,
    ) -> None:
        tenant, _, person, _ = served_client
        await _add_expired_exam(tenant.id, person.id, EXPIRED)
        async with sessionmaker() as session:
            own_company = await data_factory.create_company(
                tenant=tenant, name="Своя контора", session=session
            )
            own_person = await data_factory.create_person(
                tenant=tenant, company=own_company, last_name="Свой", session=session
            )
        await _add_expired_exam(tenant.id, own_person.id, EXPIRED)
        headers = await make_auth_headers(RoleEnum.ADMIN)

        outcome = await _collect(async_client, headers)

        assert outcome["found"] == (
            outcome["recorded"]
            + outcome["already_in_feed"]
            + outcome["not_client_related"]
            + outcome["unparsed"]
            + outcome["deferred"]
        ), outcome

    async def test_выключенный_модуль_отвечает_404(
        self, async_client: AsyncClient, make_auth_headers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import AsyncMock

        from app.api.routes import managed_clients as routes

        monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(f"{BASE}/dq-signals", headers=headers)

        assert response.status_code == 404, response.text
