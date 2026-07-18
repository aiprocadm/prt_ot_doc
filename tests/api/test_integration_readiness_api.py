from __future__ import annotations

import pytest

from app.models.models import RoleEnum, TenantIntegrationKey


@pytest.mark.anyio
async def test_integration_readiness_summary(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            TenantIntegrationKey(
                tenant_id=tenant.id,
                provider="oidc",
                encrypted_secret="opaque",
                meta_json={"issuer": "https://id.example.test", "client_id": "tenant-app"},
            )
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/integrations/readiness", headers={**headers, "X-Tenant": "test"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["webhooks"]["configured_total"] == 0
    oidc = next(item for item in body["providers"] if item["provider"] == "oidc")
    assert oidc["configured"] is True
    assert oidc["health_status"] == "contract_only"
