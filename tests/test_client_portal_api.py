from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import ClientPackagePreset, ClientPackageRun, ClientPortalToken, PackageRunStatus


def _hash(token: str) -> str:
    salt = get_settings().portal_token_salt
    return hashlib.sha256(f"{salt}:{token}".encode()).hexdigest()


@pytest.mark.anyio
async def test_portal_token_can_list_only_scoped_package(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        preset = ClientPackagePreset(code="OUT_TO_SITE", name="Out", steps_json={}, required_inputs_json=[], tenant_id=tenant.id)
        session.add(preset)
        await session.flush()
        run1 = ClientPackageRun(preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id)
        run2 = ClientPackageRun(preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id)
        session.add_all([run1, run2])
        await session.flush()
        session.add(
            ClientPortalToken(
                token_hash=_hash("scoped-token"),
                package_run_id=run1.id,
                scope_json={"package_run_ids": [run1.id], "download": True},
                expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                tenant_id=tenant.id,
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/portal/packages", params={"token": "scoped-token"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == run1.id


@pytest.mark.anyio
async def test_portal_token_cannot_access_other_package_403(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        preset = ClientPackagePreset(code="INCIDENT", name="Incident", steps_json={}, required_inputs_json=[], tenant_id=tenant.id)
        session.add(preset)
        await session.flush()
        run1 = ClientPackageRun(preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id)
        run2 = ClientPackageRun(preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id)
        session.add_all([run1, run2])
        await session.flush()
        session.add(
            ClientPortalToken(
                token_hash=_hash("scoped-token-2"),
                package_run_id=run1.id,
                scope_json={"package_run_ids": [run1.id]},
                expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
                tenant_id=tenant.id,
            )
        )
        await session.commit()

    response = await async_client.get(f"/api/v1/portal/packages/{run2.id}", params={"token": "scoped-token-2"})
    assert response.status_code == 403


@pytest.mark.anyio
async def test_portal_token_expired(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        preset = ClientPackagePreset(code="INSPECTION_PREP", name="Insp", steps_json={}, required_inputs_json=[], tenant_id=tenant.id)
        session.add(preset)
        await session.flush()
        run1 = ClientPackageRun(preset_id=preset.id, status=PackageRunStatus.RUNNING, tenant_id=tenant.id)
        session.add(run1)
        await session.flush()
        session.add(
            ClientPortalToken(
                token_hash=_hash("expired-token"),
                package_run_id=run1.id,
                scope_json={"package_run_ids": [run1.id]},
                expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
                tenant_id=tenant.id,
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/portal/packages", params={"token": "expired-token"})
    assert response.status_code == 401
