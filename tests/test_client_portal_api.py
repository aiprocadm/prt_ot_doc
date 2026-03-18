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


@pytest.mark.anyio
async def test_create_run_generates_pipeline_artifacts_and_history(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        preset = ClientPackagePreset(
            code="PIPELINE",
            name="Pipeline",
            steps_json={"steps": [{"name": "template"}]},
            required_inputs_json=[{"key": "source-doc", "title": "Source doc", "type": "file"}],
            tenant_id=tenant.id,
        )
        session.add(preset)
        await session.commit()

    headers = {"X-Tenant": tenant.id}
    response = await async_client.post("/api/v1/packages/runs", json={"preset_code": "PIPELINE"}, headers=headers)

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == PackageRunStatus.RUNNING.value
    assert payload["qc_report_json"] == {"steps": [{"name": "template", "status": "done"}]}
    assert payload["output_zip_s3_key"].startswith("packages/")
    assert payload["output_zip_s3_key"].endswith("/result.zip")
    assert payload["output_pdf_s3_key"].startswith("packages/")
    assert payload["output_pdf_s3_key"].endswith("/result.pdf")

    details = await async_client.get(f"/api/v1/packages/runs/{payload['id']}", headers=headers)
    assert details.status_code == 200
    details_payload = details.json()
    assert details_payload["status"] == PackageRunStatus.RUNNING.value

    async with sessionmaker() as session:
        run = await session.get(ClientPackageRun, payload["id"])
        assert run is not None
        token = ClientPortalToken(
            token_hash=_hash("history-token"),
            package_run_id=run.id,
            scope_json={"package_run_ids": [run.id], "download": True},
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
            tenant_id=run.tenant_id,
        )
        session.add(token)
        await session.commit()

    portal = await async_client.get(f"/api/v1/portal/packages/{payload['id']}", params={"token": "history-token"})
    assert portal.status_code == 200
    portal_payload = portal.json()
    assert portal_payload["run"]["qc_report_json"] == {"steps": [{"name": "template", "status": "done"}]}
    assert portal_payload["requirements"][0]["key"] == "source-doc"
    assert portal_payload["events"][0]["type"] == "package_run.started"
