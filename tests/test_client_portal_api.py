from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.models import ClientPackagePreset, ClientPackageRun, ClientPortalToken, PackageEvent, PackageRequirement, PackageRunStatus
from app.services.file_storage import FileStorageService


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
        session.add(ClientPortalToken(token_hash=_hash("scoped-token"), package_run_id=run1.id, scope_json={"package_run_ids": [run1.id], "download": True}, expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1), tenant_id=tenant.id))
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
        session.add(ClientPortalToken(token_hash=_hash("scoped-token-2"), package_run_id=run1.id, scope_json={"package_run_ids": [run1.id]}, expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1), tenant_id=tenant.id))
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
        session.add(ClientPortalToken(token_hash=_hash("expired-token"), package_run_id=run1.id, scope_json={"package_run_ids": [run1.id]}, expires_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1), tenant_id=tenant.id))
        await session.commit()

    response = await async_client.get("/api/v1/portal/packages", params={"token": "expired-token"})
    assert response.status_code == 401


@pytest.mark.anyio
async def test_create_run_generates_pipeline_artifacts_and_history(async_client, sessionmaker, data_factory, make_auth_headers):
    storage = FileStorageService.default()
    storage.clear()
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        preset = ClientPackagePreset(
            code="OUT_TO_SITE",
            name="Выход на объект",
            tenant_id=tenant.id,
            steps_json={"steps": [{"code": "collect_requirements"}, {"code": "publish_portal"}]},
            required_inputs_json=[
                {"key": "contract_scan", "title": "Скан договора", "type": "file"},
                {"key": "briefing_date", "title": "Дата инструктажа", "type": "text"},
            ],
        )
        session.add(preset)
        await session.commit()
        tenant_slug = tenant.slug

    headers = {**(await make_auth_headers()), "X-Tenant": tenant_slug}
    response = await async_client.post("/api/v1/packages/runs", headers=headers, json={"preset_code": "OUT_TO_SITE"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]

    details = await async_client.post(f"/api/v1/packages/runs/{run_id}/portal-link", headers=headers)
    assert details.status_code == 200
    token = details.json()["portal_url"].split("token=", 1)[1]

    portal = await async_client.get(f"/api/v1/portal/packages/{run_id}", params={"token": token})
    assert portal.status_code == 200, portal.text
    payload = portal.json()
    assert len(payload["requirements"]) == 2
    assert {event["type"] for event in payload["events"]} >= {"package_run.started", "package_run.generated", "package_run.published"}
    assert {item["kind"] for item in payload["files"]} == {"zip", "pdf"}
    assert payload["tickets"] == []

    ticket_resp = await async_client.post(f"/api/v1/portal/packages/{run_id}/tickets", params={"token": token}, json={"title": "Нужен апдейт", "message": "Пришлите новую версию"})
    assert ticket_resp.status_code == 201, ticket_resp.text

    files_response = await async_client.get(f"/api/v1/portal/packages/{run_id}/files", params={"token": token})
    assert files_response.status_code == 200
    files = files_response.json()["files"]
    assert {item["kind"] for item in files} == {"zip", "pdf", "manifest"}
    assert all(item["signed_url"] for item in files)

    async with sessionmaker() as session:
        requirements = (await session.execute(select(PackageRequirement).where(PackageRequirement.package_run_id == run_id))).scalars().all()
        events = (await session.execute(select(PackageEvent).where(PackageEvent.package_run_id == run_id))).scalars().all()
        assert len(requirements) == 2
        assert len(events) >= 4
