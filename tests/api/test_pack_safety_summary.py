"""Regression: pack safety-summary must validate the referenced run (P... #32).

The endpoint previously ignored ``pack_run_id`` entirely and returned a 200 with
arbitrary tenant persons for any id — including a non-existent or cross-tenant run.
It must now 404 on an unknown/cross-tenant run.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_pack_safety_summary_unknown_run_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.get(
        "/api/v1/packs/does-not-exist/safety-summary", headers=headers
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
