"""BIZ-51 срез-7: авто-аудит клиентов по HTTP (разд. 51.3).

Сборка отчёта проверена построчно в ``tests/test_client_audit_report.py``;
здесь — связка целиком через живой HTTP. Закрепляется:

* ручной запуск создаёт отчёт по Shared-клиенту со снимком светофора и
  изменениями периода;
* повторный запуск в тот же день не плодит отчётов — «уже есть за сегодня»
  назван числом;
* Dedicated пропускается и виден в итоге, отчёт по нему не пишется;
* список отчётов клиента — свежие сверху;
* выключенный модуль — 404.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.change_feed import ChangeStatus, ClientChangeKind
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.client_changes import ClientAuditReport, ClientChange
from app.models.managed_clients import ManagedClient
from app.models.medical import MedicalExamKind, MedicalNorm
from app.models.models import Position, RoleEnum

BASE = "/api/v1/managed-clients"


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
    """Shared-клиент с сотрудником, у должности которого есть норма медосмотра."""

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


async def _run(async_client: AsyncClient, headers) -> dict:
    response = await async_client.post(f"{BASE}/audit/run", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _reports(async_client: AsyncClient, headers, mcid: str) -> dict:
    response = await async_client.get(f"{BASE}/{mcid}/audit-reports", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.anyio
class TestClientAudit:
    async def test_запуск_создаёт_отчёт_со_снимком_и_изменениями(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, mcid = served_client
        async with await _trusted() as session:
            session.add(
                ClientChange(
                    tenant_id=tenant.id,
                    managed_client_id=mcid,
                    kind=ClientChangeKind.EMPLOYEE_HIRED,
                    happened_on=date.today() - timedelta(days=2),
                    summary="Принят: Петров Пётр",
                    status=ChangeStatus.NEW,
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        outcome = await _run(async_client, headers)

        assert outcome["created"] == 1, outcome
        body = await _reports(async_client, headers, mcid)
        assert body["total"] == 1
        report = body["items"][0]
        # Норма есть, экзамена нет вовсе → красный снимок с расшифровкой.
        assert report["overall"] == "red"
        assert "не оформлено вовсе" in report["summary"]
        assert "Изменений за период: 1" in report["summary"]
        assert "Разобрать записи ленты изменений: 1" in report["summary"]
        assert report["payload"]["changes"]["total"] == 1

    async def test_повторный_запуск_в_тот_же_день_не_дублирует(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        _, _, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _run(async_client, headers)

        outcome = await _run(async_client, headers)

        assert outcome["created"] == 0, outcome
        assert outcome["already_current"] == 1, outcome
        body = await _reports(async_client, headers, mcid)
        assert body["total"] == 1

    async def test_dedicated_пропущен_и_назван_числом(
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

        outcome = await _run(async_client, headers)

        assert outcome["skipped_dedicated"] == 1, outcome
        body = await _reports(async_client, headers, dedicated_id)
        assert body["total"] == 0

    async def test_список_свежие_сверху(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, mcid = served_client
        async with await _trusted() as session:
            for days_ago in (14, 7):
                session.add(
                    ClientAuditReport(
                        tenant_id=tenant.id,
                        managed_client_id=mcid,
                        period_start=date.today() - timedelta(days=days_ago + 7),
                        period_end=date.today() - timedelta(days=days_ago),
                        overall="green",
                        summary="Разрывов с эталоном не найдено.",
                        payload={},
                    )
                )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        body = await _reports(async_client, headers, mcid)

        ends = [item["period_end"] for item in body["items"]]
        assert ends == sorted(ends, reverse=True)

    async def test_выключенный_модуль_отвечает_404(
        self, async_client: AsyncClient, make_auth_headers, monkeypatch
    ) -> None:
        from unittest.mock import AsyncMock

        from app.api.routes import managed_clients as routes

        monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(f"{BASE}/audit/run", headers=headers)

        assert response.status_code == 404, response.text
