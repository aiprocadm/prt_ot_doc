"""HTTP: JWT выдан для tenant `test`, заголовок X-Tenant — UUID другого tenant → 403 TENANT_SCOPE_MISMATCH.

Закрывает явную регрессионную матрицу «slug mismatch» (см. tests/test_tenant_security.py) вариантом с UUID в заголовке.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import RoleEnum, Tenant


@pytest.mark.anyio
async def test_jwt_for_test_tenant_with_x_tenant_uuid_of_beta_returns_403(
    async_client,
    make_auth_headers,
    sessionmaker,
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        beta = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()

    headers["x-tenant"] = str(beta.id)

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 403
    body = response.json()
    assert body.get("code") == "TENANT_SCOPE_MISMATCH"
