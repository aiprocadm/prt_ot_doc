from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.file import File, FileScanStatus
from app.models.models import RoleEnum, Tenant


@pytest.mark.anyio
async def test_missing_x_tenant_returns_400(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers.pop("x-tenant", None)

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "tenant_required"


@pytest.mark.anyio
async def test_tenant_schema_isolation(async_client, make_auth_headers, sessionmaker) -> None:
    headers_test = await make_auth_headers(RoleEnum.ADMIN)
    headers_beta = dict(headers_test)
    headers_beta["x-tenant"] = "beta"

    create_response = await async_client.post(
        "/api/v1/companies",
        headers=headers_test,
        json={"name": "Tenant A Co", "phone_numbers": ["+7 111 111-11-11"]},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    company_id = create_response.json()["id"]

    list_beta = await async_client.get("/api/v1/companies", headers=headers_beta)
    assert list_beta.status_code == status.HTTP_200_OK
    assert all(item["id"] != company_id for item in list_beta.json()["items"])


@pytest.mark.anyio
async def test_s3_prefix_enforced(async_client, make_auth_headers, sessionmaker) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        file_row = File(
            tenant_id=tenant.id,
            storage_key="beta/foreign/report.pdf",
            bucket="documents",
            original_name="report.pdf",
            size=10,
            mime="application/pdf",
            sha256="a" * 64,
            is_quarantined=False,
            scan_status=FileScanStatus.CLEAN,
        )
        session.add(file_row)
        await session.commit()
        await session.refresh(file_row)

    response = await async_client.get(f"/api/v1/files/{file_row.id}/download", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN
