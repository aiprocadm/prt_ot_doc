from __future__ import annotations

import pytest
from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_exports_schedules_and_kpis(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    schedule = await async_client.post("/api/v1/exports/schedules", json={"name": "Daily", "dataset_code": "training", "cron_expr": "0 2 * * *", "anonymized": True}, headers={**headers, "X-Tenant": "test"})
    assert schedule.status_code == 201

    kpi = await async_client.post("/api/v1/exports/kpis", json={"code": "training_completion", "name": "Completion", "dataset_code": "training", "locale_labels": {"ru": "Завершение"}}, headers={**headers, "X-Tenant": "test"})
    assert kpi.status_code == 201

    created = await async_client.post("/api/v1/exports", json={"export_type": "analytics", "dataset_code": "training", "anonymized": True, "target_type": "webhook", "target_config": {"url": "https://example.test/hook"}}, headers={**headers, "X-Tenant": "test", "Idempotency-Key": "exp-1"})
    assert created.status_code == 201
    assert created.json()["anonymized"] is True

    listing = await async_client.get("/api/v1/exports/schedules", headers={**headers, "X-Tenant": "test"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
