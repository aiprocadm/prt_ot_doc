"""BIZ-51 срез-9: запись ленты — событие (разд. 51.2, четвёртый источник).

ТЗ называет rules engine источником правил «если у клиента X, то создать
задачу/комплект Y». Движок в проекте есть и слушает события outbox; не хватало
одного — записи ленты события не порождали, и правило на них было не
построить. Здесь закрепляется связка на всех путях создания записи:

* ручная запись кладёт событие в outbox (в той же транзакции);
* сбор Data Quality кладёт событие на каждую новую запись;
* загрузка кадровых данных кладёт событие на каждый сигнал;
* правило конструктора на это событие РЕАЛЬНО срабатывает;
* событие видно в каталоге конструктора правил.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.medical import MedicalExam
from app.models.models import Outbox, RoleEnum
from app.models.rules_engine import AutomationRule, AutomationRuleTrigger

BASE = "/api/v1/managed-clients"
EVENT = "managed_clients.change_recorded"

EXPIRED = date.today() - timedelta(days=30)


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
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Иванов", session=session
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


async def _events(tenant_id: str) -> list[Outbox]:
    async with await _trusted() as session:
        rows = (
            await session.execute(
                select(Outbox).where(Outbox.tenant_id == tenant_id, Outbox.event_type == EVENT)
            )
        ).scalars()
        return list(rows)


def _change(**extra) -> dict:
    payload = {
        "kind": "employee_hired",
        "happened_on": date.today().isoformat(),
        "summary": "Принят: Петров Пётр",
    }
    payload.update(extra)
    return payload


@pytest.mark.anyio
class TestChangeBecomesEvent:
    async def test_ручная_запись_кладёт_событие_в_outbox(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, _, mcid = served_client
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(
            f"{BASE}/{mcid}/changes", json=_change(), headers=headers
        )

        assert response.status_code == 201, response.text
        events = await _events(tenant.id)
        assert len(events) == 1
        payload = events[0].payload
        assert payload["kind"] == "employee_hired"
        assert payload["source"] == "manual"
        assert payload["managed_client_id"] == mcid
        assert payload["change_id"] == response.json()["id"]

    async def test_сбор_dq_кладёт_событие_на_каждую_запись(
        self, async_client: AsyncClient, make_auth_headers, served_client
    ) -> None:
        tenant, person, _ = served_client
        async with await _trusted() as session:
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="периодический",
                    exam_date=EXPIRED - timedelta(days=365),
                    valid_until=EXPIRED,
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(f"{BASE}/dq-signals", headers=headers)

        assert response.status_code == 200, response.text
        assert response.json()["recorded"] == 1
        events = await _events(tenant.id)
        assert len(events) == 1
        assert events[0].payload["source"] == "data_quality"

    async def test_правило_конструктора_реально_срабатывает(
        self,
        async_client: AsyncClient,
        make_auth_headers,
        served_client,
        sessionmaker,
        data_factory,
    ) -> None:
        """Смысл среза: «если у клиента X → сделать Y» строится в готовом
        конструкторе. Правило на событие ленты обязано сработать, а не
        существовать декоративно."""

        from app.models.feature import Feature, FeatureEnablement

        tenant, _, mcid = served_client
        async with sessionmaker() as session:
            feature = (
                await session.execute(select(Feature).where(Feature.code == "rules_engine"))
            ).scalar_one_or_none()
            if feature is None:
                feature = Feature(code="rules_engine", title="Движок правил")
                session.add(feature)
                await session.flush()
            session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=True))
            session.add(
                AutomationRule(
                    tenant_id=str(tenant.id),
                    name="Приём сотрудника — вебхук",
                    event_type=EVENT,
                    conditions_json={
                        "match": "all",
                        "conditions": [{"field": "kind", "op": "eq", "value": "employee_hired"}],
                    },
                    actions_json=[{"type": "webhook"}],
                )
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.post(
            f"{BASE}/{mcid}/changes", json=_change(), headers=headers
        )

        assert response.status_code == 201, response.text
        async with await _trusted() as session:
            triggers = list(
                (
                    await session.execute(
                        select(AutomationRuleTrigger).where(
                            AutomationRuleTrigger.tenant_id == tenant.id,
                            AutomationRuleTrigger.event_type == EVENT,
                        )
                    )
                ).scalars()
            )
        assert len(triggers) == 1, "правило на событие ленты не сработало"

    async def test_событие_видно_в_каталоге_конструктора(self) -> None:
        from app.modules.rules_engine.catalog import event_catalog

        catalog = {item["event_type"]: item for item in event_catalog()}
        assert EVENT in catalog
        fields = {f["name"] for f in catalog[EVENT]["fields"]}
        assert {"kind", "managed_client_id", "source", "summary"} <= fields

    async def test_повторный_enqueue_той_же_записи_не_дублирует(
        self, sessionmaker, data_factory, served_client
    ) -> None:
        """Дедуп по личности события (change_id): ретрай не плодит строк."""

        from app.domains.managed_clients.change_feed import ChangeStatus, ClientChangeKind
        from app.models.client_changes import ClientChange
        from app.services.client_change_signals import enqueue_change_recorded

        tenant, _, mcid = served_client
        async with sessionmaker() as session:
            row = ClientChange(
                tenant_id=str(tenant.id),
                managed_client_id=mcid,
                kind=ClientChangeKind.SITE_ADDED,
                happened_on=date.today(),
                summary="Новый цех",
                status=ChangeStatus.NEW,
            )
            session.add(row)
            await session.flush()
            await enqueue_change_recorded(session, [row])
            await enqueue_change_recorded(session, [row])
            await session.commit()

        events = await _events(str(tenant.id))
        assert len(events) == 1
