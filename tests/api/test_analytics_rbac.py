"""RBAC hardening: analytics + export_center routers; operational dedup pin."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

ROUTE_GROUPS = Path(__file__).resolve().parents[2] / "backend/app/api/v1/route_groups.py"


async def _tenant(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()


@pytest.mark.asyncio
async def test_analytics_read_rbac(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _tenant(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)
    for path in (
        "/api/v1/analytics/dashboard/executive",
        "/api/v1/analytics/dashboard/overdue",
        "/api/v1/analytics/trends/incidents",
    ):
        resp = await async_client.get(path, headers=worker)
        assert resp.status_code == status.HTTP_403_FORBIDDEN, path

    line_manager = await make_auth_headers(RoleEnum.LINE_MANAGER)
    ok = await async_client.get("/api/v1/analytics/dashboard/overdue", headers=line_manager)
    assert ok.status_code == status.HTTP_200_OK
    hr = await make_auth_headers(RoleEnum.HR)
    ok2 = await async_client.get("/api/v1/analytics/trends/incidents", headers=hr)
    assert ok2.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_analytics_recompute_admin_only(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _tenant(sessionmaker, data_factory)
    line_manager = await make_auth_headers(RoleEnum.LINE_MANAGER)
    denied = await async_client.post("/api/v1/analytics/recompute", headers=line_manager)
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    admin = await make_auth_headers(RoleEnum.ADMIN)
    ok = await async_client.post("/api/v1/analytics/recompute", headers=admin)
    assert ok.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_export_center_rbac(async_client, make_auth_headers, sessionmaker, data_factory):
    await _tenant(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)
    assert (
        await async_client.get("/api/v1/exports", headers=worker)
    ).status_code == status.HTTP_403_FORBIDDEN
    assert (
        await async_client.post(
            "/api/v1/exports",
            json={"export_type": "reports:test"},
            headers=worker,
        )
    ).status_code == status.HTTP_403_FORBIDDEN

    accountant = await make_auth_headers(RoleEnum.ACCOUNTANT)
    assert (
        await async_client.get("/api/v1/exports", headers=accountant)
    ).status_code == status.HTTP_200_OK

    admin = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/exports", json={"export_type": "reports:test"}, headers=admin
    )
    assert created.status_code == status.HTTP_201_CREATED


def test_operational_dashboard_registered_once() -> None:
    src = ROUTE_GROUPS.read_text(encoding="utf-8")
    assert src.count("(operational_dashboard.router") == 1
