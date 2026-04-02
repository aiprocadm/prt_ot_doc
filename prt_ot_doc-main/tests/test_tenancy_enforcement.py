from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum
from app.modules.files import storage


@pytest.mark.anyio
async def test_missing_x_tenant_returns_400(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers.pop("x-tenant", None)

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "TENANT_REQUIRED"


@pytest.mark.anyio
async def test_invalid_x_tenant_uuid_returns_400(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["x-tenant"] = "not-a-uuid"

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "TENANT_INVALID"


@pytest.mark.anyio
async def test_valid_uuid_x_tenant_returns_success(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/tenants", headers=headers)
    assert response.status_code != status.HTTP_400_BAD_REQUEST


def test_s3_tenant_key_isolation() -> None:
    key = storage.build_tenant_key(
        tenant_id="11111111-1111-1111-1111-111111111111",
        entity="documents",
        entity_id="doc-1",
        file_id="file-1",
        filename="contract.pdf",
    )
    assert key.startswith("tenants/11111111-1111-1111-1111-111111111111/")

    with pytest.raises(PermissionError):
        storage.assert_tenant_key(
            tenant_id="22222222-2222-2222-2222-222222222222",
            key=key,
        )
