from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.models import Company, Site, Tenant
from app.models.npa import NpaAct, NpaClause
from app.models.risk import Risk
from app.services.risk import RiskLevelError, RiskService


@pytest.mark.anyio
async def test_npa_endpoint_returns_acts_with_clauses(
    async_client, sessionmaker, make_auth_headers
):
    async with sessionmaker() as session:
        act = NpaAct(
            code="TR-001",
            title="Test Regulation",
            edition="2023",
            valid_from=date(2023, 1, 1),
            valid_to=None,
        )
        act.clauses.extend(
            [
                NpaClause(code="1", text="Clause one"),
                NpaClause(code="2", text="Clause two"),
            ]
        )
        session.add(act)

        other_act = NpaAct(
            code="TR-002",
            title="Archived Regulation",
            edition="2018",
            valid_from=date(2018, 6, 1),
            valid_to=date(2020, 12, 31),
        )
        session.add(other_act)
        await session.commit()

    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/npa", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2

    first = payload["items"][0]
    assert first["code"] == "TR-001"
    assert [clause["code"] for clause in first["clauses"]] == ["1", "2"]


@pytest.mark.anyio
async def test_risk_service_calculation_bounds() -> None:
    assert RiskService.calculate(2, 3) == 6
    with pytest.raises(RiskLevelError):
        RiskService.calculate(0, 3)
    with pytest.raises(RiskLevelError):
        RiskService.calculate(6, 3)


@pytest.mark.anyio
async def test_risk_endpoint_returns_report(async_client, sessionmaker, make_auth_headers):
    headers = await make_auth_headers()
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        company = Company(tenant_id=tenant.id, name="Risky Corp")
        session.add(company)
        await session.flush()

        site = Site(tenant_id=tenant.id, company_id=company.id, name="Main Site")
        session.add(site)
        await session.flush()

        other_site = Site(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Backup Site",
        )
        session.add(other_site)
        await session.flush()

        session.add_all(
            [
                Risk(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    hazard="Unshielded machinery",
                    probability=3,
                    severity=4,
                    level=RiskService.calculate(3, 4),
                    controls="Install guards",
                ),
                Risk(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=site.id,
                    hazard="Chemical exposure",
                    probability=2,
                    severity=5,
                    level=RiskService.calculate(2, 5),
                    controls="Provide PPE",
                ),
                Risk(
                    tenant_id=tenant.id,
                    company_id=company.id,
                    site_id=other_site.id,
                    hazard="Slippery floors",
                    probability=1,
                    severity=2,
                    level=RiskService.calculate(1, 2),
                    controls="Improve cleaning",
                ),
            ]
        )

        await session.commit()

    response = await async_client.get(f"/api/v1/risks?site_id={site.id}", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert len(payload["items"]) == 2
    assert payload["report"]["total"] == 2
    assert payload["report"]["highest_level"] == 12
    assert payload["report"]["distribution"] == {"10": 1, "12": 1}

    response_all = await async_client.get("/api/v1/risks", headers=headers)
    assert response_all.status_code == 200
    payload_all = response_all.json()
    assert len(payload_all["items"]) == 3
    assert payload_all["report"]["total"] == 3

    not_found = await async_client.get("/api/v1/risks?site_id=does-not-exist", headers=headers)
    assert not_found.status_code == 404
