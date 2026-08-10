"""PPE writes must outlive the request session (P10-06 §12.4).

Regression guard for the silent-discard class: every ``/api/v1/ppe/*`` write
handler is flush-only, so before ``get_session`` owned the request transaction
these endpoints returned 201 with a populated body while the row was thrown
away when the session closed. The assertions here deliberately read back through
a SEPARATE session — asserting against the request session would pass even with
the write discarded, which is why the original suite never caught this.

The dependency-level contract is pinned in
``tests/test_api_dependencies.py::test_get_session_commits_on_clean_exit``.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.models.ppe import PPESafetyBudget, PPESupplier
from tests.utils.factories import TestDataFactory


async def _set_warehouse_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool) -> None:
    """Mirrors ``tests/api/test_ppe_shortage_api.py::_set_warehouse_flag``."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        # Обновляем существующую строку, а не добавляем вторую: у арендатора
        # уже есть выдача модуля (BIZ-61 срез-2 — модуль по умолчанию выключен,
        # поэтому тестовым арендаторам он выдаётся явно). Вставка дубля делала
        # ответ гейта неопределённым.
        enablement = (
            (
                await session.execute(
                    select(FeatureEnablement).where(
                        FeatureEnablement.tenant_id == tenant.id,
                        FeatureEnablement.feature_id == feature.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if enablement is None:
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            enablement.on = on
        await session.commit()


@pytest.mark.asyncio
async def test_created_supplier_survives_the_request(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    await _set_warehouse_flag(sessionmaker, data_factory, on=True)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        "/api/v1/ppe/suppliers", json={"name": "ООО Спецодежда"}, headers=headers
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    supplier_id = resp.json()["id"]

    async with sessionmaker() as fresh:
        row = await fresh.get(PPESupplier, supplier_id)

    assert row is not None, "POST /ppe/suppliers returned 201 but persisted nothing"
    assert row.name == "ООО Спецодежда"


@pytest.mark.asyncio
async def test_created_budget_survives_the_request(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    """Blocks the §12.4 contour: /budget/overview reads ppe_safety_budget."""

    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        "/api/v1/ppe/budgets",
        json={
            "name": "Бюджет СИЗ 2026",
            "period_start": "2026-01-01",
            "period_end": "2026-12-31",
            "planned_amount": 500000,
        },
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    budget_id = resp.json()["id"]

    async with sessionmaker() as fresh:
        row = await fresh.get(PPESafetyBudget, budget_id)

    assert row is not None, "POST /ppe/budgets returned 201 but persisted nothing"
    assert row.name == "Бюджет СИЗ 2026"
