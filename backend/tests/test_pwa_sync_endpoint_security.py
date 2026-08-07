from __future__ import annotations

from types import MappingProxyType, SimpleNamespace

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.pwa_sync import commit_media, create_batch, sync_status
from app.core.security import AccessContext
from app.db.session import TenantBase
from app.models.models import OfflineMediaQueue, OfflineSyncBatch


def _access_ctx(
    *, user_id: str, tenant_id: str, tenant_slug: str, role: str = "employee"
) -> AccessContext:
    user = SimpleNamespace(
        id=user_id,
        email=f"{user_id}@tenant.test",
        role=SimpleNamespace(value=role),
        company_id=None,
    )
    return AccessContext(
        user=user,
        claims=MappingProxyType(
            {
                "sub": user_id,
                "tenant": tenant_slug,
                "tenant_id": tenant_id,
                "role": role,
                "roles": [role],
            }
        ),
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        company_id=None,
    )


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_batch_ignores_spoofed_user_and_status(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    access = _access_ctx(user_id="user-1", tenant_id=tenant.id, tenant_slug=tenant.slug)

    payload = {
        "user_id": "spoofed-user",
        "status": "failed",
        "device_id": "device-1",
        "entity_type": "task_comment",
        "payload": {"entity_type": "task_comment", "comment": "offline"},
    }

    result = await create_batch(payload=payload, tenant=tenant, session=db_session, access=access)

    stored = await db_session.get(OfflineSyncBatch, result.id)
    assert stored is not None
    assert stored.user_id == "user-1"
    assert stored.tenant_id == "tenant-1"


@pytest.mark.asyncio
async def test_sync_status_forbids_non_owner_non_admin(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    owner = _access_ctx(user_id="owner-1", tenant_id=tenant.id, tenant_slug=tenant.slug)
    stranger = _access_ctx(user_id="stranger-1", tenant_id=tenant.id, tenant_slug=tenant.slug)

    created = await create_batch(
        payload={
            "device_id": "device-1",
            "entity_type": "incident",
            "payload": {"entity_type": "incident", "title": "draft"},
        },
        tenant=tenant,
        session=db_session,
        access=owner,
    )

    with pytest.raises(Exception) as exc:
        await sync_status(batch_id=created.id, tenant=tenant, session=db_session, access=stranger)
    assert getattr(exc.value, "status_code", None) == 403


@pytest.mark.asyncio
async def test_commit_media_ignores_spoofed_owner_and_upload_status(db_session) -> None:
    tenant = SimpleNamespace(id="tenant-1", slug="tenant-a", name="Tenant A")
    access = _access_ctx(user_id="field-user", tenant_id=tenant.id, tenant_slug=tenant.slug)

    payload = {
        "user_id": "spoofed-user",
        "upload_status": "uploaded",
        "device_id": "device-1",
        "local_ref": "photo://abc",
        "metadata_json": {"kind": "photo"},
    }

    result = await commit_media(payload=payload, tenant=tenant, session=db_session, access=access)

    stored = await db_session.get(OfflineMediaQueue, result.id)
    assert stored is not None
    assert stored.user_id == "field-user"
    assert stored.tenant_id == "tenant-1"
