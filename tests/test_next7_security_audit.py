from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import issue_access_token
from app.models.models import AuditLog, Company, RoleEnum, Tenant, User
from app.services.auth import hash_password


@pytest.mark.anyio("asyncio")
async def test_rbac_admin_only_route(async_client: AsyncClient, make_auth_headers) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.OT_SPECIALIST)}
    resp = await async_client.get("/api/v1/admin/users/non-existent/roles", headers=headers)
    assert resp.status_code == 403


@pytest.mark.anyio("asyncio")
async def test_abac_company_scope_list(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        user = User(
            tenant_id=tenant.id,
            email="abac-list@example.com",
            full_name="ABAC",
            role=RoleEnum.ADMIN,
            hashed_password=hash_password("x"),
        )
        c1 = Company(tenant_id=tenant.id, name="Allowed Co")
        c2 = Company(tenant_id=tenant.id, name="Denied Co")
        session.add_all([user, c1, c2])
        await session.commit()
        token = issue_access_token(
            subject=user.id,
            tenant=tenant.slug,
            role=user.role.value,
            additional_claims={"tenant_id": tenant.id, "company_ids": [c1.id]},
        )

    headers = {**dict(async_client.headers), "Authorization": f"Bearer {token}", "x-tenant": "test"}
    resp = await async_client.get("/api/v1/companies", headers=headers)
    assert resp.status_code == 200
    names = {item["name"] for item in resp.json()["items"]}
    assert names == {"Allowed Co"}


@pytest.mark.anyio("asyncio")
async def test_abac_company_scope_get_forbidden(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        user = User(
            tenant_id=tenant.id,
            email="abac-get@example.com",
            full_name="ABAC",
            role=RoleEnum.ADMIN,
            hashed_password=hash_password("x"),
        )
        allowed = Company(tenant_id=tenant.id, name="Allowed Get")
        denied = Company(tenant_id=tenant.id, name="Denied Get")
        session.add_all([user, allowed, denied])
        await session.commit()
        token = issue_access_token(
            subject=user.id,
            tenant=tenant.slug,
            role=user.role.value,
            additional_claims={"tenant_id": tenant.id, "company_ids": [allowed.id]},
        )

    headers = {**dict(async_client.headers), "Authorization": f"Bearer {token}", "x-tenant": "test"}
    resp = await async_client.get(f"/api/v1/companies/{denied.id}", headers=headers)
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "forbidden"
    assert body["detail"]["type"] == "policy"


@pytest.mark.anyio("asyncio")
async def test_audit_written_on_update_with_field_diff(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    make_auth_headers,
) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}
    create = await async_client.post(
        "/api/v1/companies",
        headers=headers,
        json={"name": "Audit Co", "inn": "123"},
    )
    assert create.status_code == 201
    company_id = create.json()["id"]

    update = await async_client.patch(
        f"/api/v1/companies/{company_id}",
        headers=headers,
        json={"name": "Audit Co Updated"},
    )
    assert update.status_code == 200

    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(AuditLog)
                .where(AuditLog.object_type == "Company", AuditLog.object_id == company_id)
                .order_by(AuditLog.when.desc())
            )
        ).scalars().all()
        assert rows
        assert rows[0].changed_fields["changed"]["name"]["from"] == "Audit Co"
        assert rows[0].changed_fields["changed"]["name"]["to"] == "Audit Co Updated"


@pytest.mark.anyio("asyncio")
async def test_audit_immutable(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        await session.execute(delete(AuditLog))
        await session.commit()

        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = AuditLog(
            tenant_id=tenant.id,
            user_id=None,
            action="update",
            object_type="Company",
            object_id="obj",
            ip="127.0.0.1",
        )
        session.add(entry)
        await session.commit()

        entry.action = "delete"
        with pytest.raises(RuntimeError):
            await session.flush()
        await session.rollback()

        with pytest.raises(RuntimeError):
            await session.delete(entry)
            await session.flush()
