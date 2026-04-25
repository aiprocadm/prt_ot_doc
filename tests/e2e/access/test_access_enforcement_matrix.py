from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import verify_token
from app.models.models import RoleEnum, User


@pytest.mark.anyio
async def test_direct_api_create_is_denied_for_low_privilege_user(
    async_client,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers(RoleEnum.STUDENT)

    response = await async_client.post(
        "/api/v1/training/programs",
        json={"title": "Should be denied"},
        headers=headers,
    )

    assert response.status_code == 403
    body = response.json()
    assert body["detail"]["code"] == "AUTHZ_DENIED"


@pytest.mark.anyio
async def test_cross_tenant_header_is_denied_even_for_privileged_user(
    async_client,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["x-tenant"] = "acme"

    response = await async_client.post(
        "/api/v1/training/programs",
        json={"title": "Cross tenant"},
        headers=headers,
    )

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "TENANT_SCOPE_MISMATCH"


@pytest.mark.anyio
async def test_stale_admin_token_is_denied_after_role_downgrade(
    async_client,
    make_auth_headers,
    sessionmaker,
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN, email="stale-admin@example.com")
    token = headers["Authorization"].split(" ", 1)[1]
    claims = verify_token(token, expected_type="access")
    user_id = str(claims["sub"])

    async with sessionmaker() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = RoleEnum.STUDENT
        user.roles = []
        await session.commit()

    stale_token_response = await async_client.post(
        "/api/v1/training/programs",
        json={"title": "Should fail after downgrade"},
        headers=headers,
    )

    assert stale_token_response.status_code == 403
    assert stale_token_response.json()["detail"]["code"] == "AUTHZ_DENIED"


@pytest.mark.anyio
@pytest.mark.usefixtures("aws")
async def test_file_detail_denies_client_from_other_company(
    async_client,
    make_auth_headers,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="Uploader Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="Viewer Co", session=session)
        await session.commit()

    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    upload = await async_client.post(
        "/api/v1/files-legacy/upload",
        files={"file": ("company-note.txt", b"matrix", "text/plain")},
        data={"company_id": company_a.id},
        headers=admin_headers,
    )
    assert upload.status_code == 201
    file_id = upload.json()["id"]

    other_company_headers = await make_auth_headers(
        RoleEnum.CLIENT_USER,
        email="other-company-client@example.com",
        company_id=company_b.id,
    )

    detail = await async_client.get(
        f"/api/v1/files-legacy/{file_id}", headers=other_company_headers
    )

    assert detail.status_code == 403
