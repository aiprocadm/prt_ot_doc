from __future__ import annotations

import pytest
from app.models.models import RoleEnum
from app.models.safety_core import RiskMeasure


@pytest.mark.anyio
async def test_advanced_risk_methodology_and_map(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        measure = RiskMeasure(tenant_id=tenant.id, name="PPE", effectiveness_score=20)
        session.add(measure)
        await session.commit()
        await session.refresh(measure)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    methodology = await async_client.post(
        "/api/v1/risk/advanced/methodologies",
        json={"code": "fk-1", "name": "Fine Kinney", "type": "fine_kinney", "formula_json": {"ranges": [{"min": 0, "max": 20, "level": "low"}, {"min": 21, "max": 70, "level": "medium"}, {"min": 71, "max": 200, "level": "high"}, {"min": 201, "max": 10000, "level": "critical"}]}},
        headers={**headers, "X-Tenant": "test"},
    )
    assert methodology.status_code == 201

    risk_map = await async_client.post(
        "/api/v1/risk/advanced/maps",
        json={"entity_type": "site", "entity_id": "site-1", "risk_methodology_id": methodology.json()["id"]},
        headers={**headers, "X-Tenant": "test"},
    )
    assert risk_map.status_code == 201

    item = await async_client.post(
        f"/api/v1/risk/advanced/maps/{risk_map.json()['id']}/items",
        json={"hazard_id": "haz-1", "probability_value": 2, "severity_value": 5, "exposure_value": 3, "measure_ids": [measure.id]},
        headers={**headers, "X-Tenant": "test"},
    )
    assert item.status_code == 201

    recalc = await async_client.post(f"/api/v1/risk/advanced/maps/{risk_map.json()['id']}/recalculate", headers={**headers, "X-Tenant": "test"})
    assert recalc.status_code == 200

    summary = await async_client.get(f"/api/v1/risk/advanced/maps/{risk_map.json()['id']}/summary", headers={**headers, "X-Tenant": "test"})
    assert summary.status_code == 200
    assert summary.json()["items_total"] == 1
    assert "risk_zones" in summary.json()

    custom = await async_client.post(
        "/api/v1/risk/advanced/methodologies",
        json={
            "code": "custom-1",
            "name": "Custom Weighted",
            "type": "custom",
            "formula_json": {"strategy": "weighted_sum", "coefficients": {"probability": 2, "severity": 3, "exposure": 1}},
            "scale_json": {"level_rules": [{"min": 0, "max": 10, "level": "low"}, {"min": 10.01, "max": 20, "level": "medium"}, {"min": 20.01, "max": 1000, "level": "high"}]},
        },
        headers={**headers, "X-Tenant": "test"},
    )
    assert custom.status_code == 201

    clone = await async_client.post(
        f"/api/v1/risk/advanced/methodologies/{custom.json()['id']}/clone",
        json={},
        headers={**headers, "X-Tenant": "test"},
    )
    assert clone.status_code == 201

    activated = await async_client.post(
        f"/api/v1/risk/advanced/methodologies/{clone.json()['id']}/activate",
        headers={**headers, "X-Tenant": "test"},
    )
    assert activated.status_code == 200
