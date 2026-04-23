from __future__ import annotations

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes.pwa_sync import _sanitize_offline_entity_payload
from app.db.session import TenantBase
from app.models.models import OfflineSyncBatch
from app.modules.pwa_sync.services import OfflineSyncService


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
async def test_evidence_case_create_then_duplicate_conflict(db_session) -> None:
    service = OfflineSyncService()
    first = OfflineSyncBatch(
        tenant_id="tenant-1",
        user_id="user-1",
        device_id="device-1",
        status="pending",
        entity_type="evidence_case",
        payload={"operation": "create", "evidence_case_id": "ev-1"},
    )
    db_session.add(first)
    await db_session.flush()
    await service.apply_batch(db_session, first)
    assert first.status == "applied"
    assert first.payload["version"] == 1

    second = OfflineSyncBatch(
        tenant_id="tenant-1",
        user_id="user-1",
        device_id="device-1",
        status="pending",
        entity_type="evidence_case",
        payload={"operation": "create", "evidence_case_id": "ev-1"},
    )
    db_session.add(second)
    await db_session.flush()
    await service.apply_batch(db_session, second)
    assert second.status == "failed"
    assert second.error_payload["error"] == "conflict_evidence_case_exists"


@pytest.mark.asyncio
async def test_evidence_case_update_conflict_then_client_retry_resolution(db_session) -> None:
    service = OfflineSyncService()
    base = OfflineSyncBatch(
        tenant_id="tenant-1",
        user_id="user-1",
        device_id="device-1",
        status="pending",
        entity_type="evidence_case",
        payload={"operation": "create", "evidence_case_id": "ev-2"},
    )
    db_session.add(base)
    await db_session.flush()
    await service.apply_batch(db_session, base)
    assert base.payload["version"] == 1

    conflict_update = OfflineSyncBatch(
        tenant_id="tenant-1",
        user_id="user-1",
        device_id="device-1",
        status="pending",
        entity_type="evidence_case",
        payload={"operation": "update", "evidence_case_id": "ev-2", "base_version": 99},
    )
    db_session.add(conflict_update)
    await db_session.flush()
    await service.apply_batch(db_session, conflict_update)
    assert conflict_update.status == "failed"
    assert conflict_update.error_payload["error"] == "conflict_evidence_case_version_mismatch"

    resolved = await service.resolve_conflict(
        db_session,
        batch=conflict_update,
        strategy="client_retry",
        payload_patch={"base_version": 1},
    )
    assert resolved.status == "pending"
    assert resolved.payload["base_version"] == 1
    assert resolved.error_payload["resolved_by"] == "client_retry"


def test_sanitize_offline_payload_strips_tenant_and_user_fields() -> None:
    payload = {
        "tenant_id": "foreign-tenant",
        "user_id": "foreign-user",
        "evidence_case_id": "ev-4",
        "meta": {
            "tenant_slug": "foreign",
            "company_id": "c-1",
            "safe": True,
        },
        "items": [{"tenant_id": "another", "ok": "yes"}],
    }

    safe = _sanitize_offline_entity_payload(payload)
    assert safe == {
        "evidence_case_id": "ev-4",
        "meta": {"safe": True},
        "items": [{"ok": "yes"}],
    }
