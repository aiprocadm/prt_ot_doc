"""BIZ-49 срез-17 — перенос норм медосмотров и СИЗ (разд. 49.1).

Нормы висят на должности, а должность переехала в срезе-16. Без норм у
клиента не считается ни периодичность медосмотров, ни положенные СИЗ:
контроль допуска молча падает на «сойдёт любой действующий осмотр».
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.master_data import Company, Position, Site
from app.models.medical import MedicalExamKind, MedicalNorm
from app.models.models import Tenant
from app.models.ppe import PPEItem, PPENorm
from app.models.risk import RiskHazard

_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="admin-1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["admin"], company_id=None)


def _request():
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))


class _TrustedWrapper:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._orig_commit = self._session.commit
        self._session.commit = self._session.flush
        return self._session

    async def __aexit__(self, *exc):
        self._session.commit = self._orig_commit
        return False


async def _setup(session):
    company = Company(tenant_id=_TENANT, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    position = Position(tenant_id=_TENANT, company_id=company.id, name="Слесарь")
    session.add(position)
    session.add(
        Tenant(
            slug="romashka",
            code="romashka",
            name="Ромашка",
            schema_name="tenant_romashka",
            contact_email="r@r.ru",
        )
    )
    client = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        company_id=company.id,
        dedicated_tenant_slug="romashka",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    await session.flush()
    return SimpleNamespace(client=client, company=company, position=position)


async def _transfer(session, mcid):
    with patch.object(routes, "_trusted_session", lambda: _TrustedWrapper(session)):
        return await routes.transfer_client_data(
            mcid=mcid,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )


async def _target_id(session) -> str:
    row = (await session.execute(select(Tenant).where(Tenant.slug == "romashka"))).scalar_one()
    return row.id


@pytest.mark.asyncio
async def test_norms_follow_the_position(sessionmaker):
    async with sessionmaker() as session:
        env = await _setup(session)
        hazard = RiskHazard(tenant_id=_TENANT, code="NOISE", title="Шум")
        item = PPEItem(tenant_id=_TENANT, name="Наушники")
        session.add_all([hazard, item])
        await session.flush()
        session.add(
            MedicalNorm(
                tenant_id=_TENANT,
                position_id=env.position.id,
                hazard_id=hazard.id,
                exam_kind=MedicalExamKind.PERIODIC,
                interval_days=365,
            )
        )
        session.add(
            PPENorm(
                tenant_id=_TENANT,
                position_id=env.position.id,
                hazard_id=hazard.id,
                item_id=item.id,
                item_name="Наушники",
                quantity=1,
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["medical_norms"] == 1
        assert out.counts["ppe_norms"] == 1
        assert out.counts["risk_hazards"] == 1

        target = await _target_id(session)
        new_position = (
            await session.execute(select(Position).where(Position.tenant_id == target))
        ).scalar_one()
        new_hazard = (
            await session.execute(select(RiskHazard).where(RiskHazard.tenant_id == target))
        ).scalar_one()
        med = (
            await session.execute(select(MedicalNorm).where(MedicalNorm.tenant_id == target))
        ).scalar_one()
        ppe = (
            await session.execute(select(PPENorm).where(PPENorm.tenant_id == target))
        ).scalar_one()
        new_item = (
            await session.execute(select(PPEItem).where(PPEItem.tenant_id == target))
        ).scalar_one()

        # Нормы сшиты с КОПИЯМИ должности, опасности и номенклатуры.
        assert med.position_id == new_position.id
        assert med.hazard_id == new_hazard.id
        assert ppe.position_id == new_position.id
        assert ppe.hazard_id == new_hazard.id
        assert ppe.item_id == new_item.id
        assert med.interval_days == 365
        # Карточка опасности едет без файла обоснования (он у аутсорсера).
        assert new_hazard.document_file_id is None


@pytest.mark.asyncio
async def test_medical_norm_without_hazard_survives(sessionmaker):
    """Норма «по должности вообще» (hazard_id NULL) — законный случай."""

    async with sessionmaker() as session:
        env = await _setup(session)
        session.add(
            MedicalNorm(
                tenant_id=_TENANT,
                position_id=env.position.id,
                hazard_id=None,
                exam_kind=MedicalExamKind.PRELIMINARY,
                interval_days=730,
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["medical_norms"] == 1
        assert out.counts["risk_hazards"] == 0

        target = await _target_id(session)
        med = (
            await session.execute(select(MedicalNorm).where(MedicalNorm.tenant_id == target))
        ).scalar_one()
        assert med.hazard_id is None
        assert med.interval_days == 730


@pytest.mark.asyncio
async def test_norms_of_other_company_positions_stay(sessionmaker):
    """Норма чужой должности не переносится — должность не наша."""

    async with sessionmaker() as session:
        env = await _setup(session)
        other_company = Company(tenant_id=_TENANT, name="ООО Чужая")
        session.add(other_company)
        await session.flush()
        other_position = Position(
            tenant_id=_TENANT, company_id=other_company.id, name="Чужая должность"
        )
        session.add(other_position)
        await session.flush()
        session.add(
            MedicalNorm(
                tenant_id=_TENANT,
                position_id=other_position.id,
                exam_kind=MedicalExamKind.PERIODIC,
                interval_days=365,
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["medical_norms"] == 0

        target = await _target_id(session)
        norms = (
            (await session.execute(select(MedicalNorm).where(MedicalNorm.tenant_id == target)))
            .scalars()
            .all()
        )
        assert norms == []
        # Площадок у этой организации нет — проверяем, что перенос не создал их.
        sites = (
            (await session.execute(select(Site).where(Site.tenant_id == target))).scalars().all()
        )
        assert sites == []
