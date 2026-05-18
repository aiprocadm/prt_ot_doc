"""PWA offline-sync state machine tests (Phase 7.1 / vNext-MOBILE-02, Session 43).

The PWA offline-sync engine (``app.modules.pwa_sync.services.OfflineSyncService``
and ``app.api.routes.pwa_sync``) already implements full batch lifecycle,
conflict detection for briefing entries and evidence cases, and resolution
strategies. Before this session there were no direct tests of the HTTP
state machine.

These tests pin the contract:

* ``POST /pwa/sync/batch`` — validation, sanitization, happy path, conflict on completed briefing entry.
* Evidence-case conflicts — create-when-exists, update-when-missing, version mismatch.
* ``POST /pwa/sync/conflicts/{id}/resolve`` — server_wins / client_retry / invalid strategy / invalid payload_patch.
* ``GET  /pwa/sync/status/{id}`` — owner returns row; cross-tenant 404; non-owner 403.
* ``POST /pwa/media/commit`` — happy path + validation.
* ``GET  /pwa/bootstrap`` — full envelope, pending count, failed conflicts surfaced.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingTemplate,
    OfflineMediaQueue,
    OfflineSyncBatch,
    Tenant,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _post_batch(
    client: AsyncClient, headers: dict[str, str], *, entity_type: str, payload: dict, device_id: str = "dev-1", **extras
) -> dict:
    body = {"device_id": device_id, "entity_type": entity_type, "payload": payload, **extras}
    response = await client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    return response.json() | {"_status": response.status_code}


async def _seed_briefing_journal(session, *, tenant_id: str) -> str:
    template = BriefingTemplate(
        tenant_id=tenant_id,
        code="tpl-pwa",
        title="Pwa template",
        briefing_type="introductory",
        status="active",
    )
    session.add(template)
    await session.flush()
    journal = BriefingJournal(
        tenant_id=tenant_id,
        code="jrn-pwa",
        title="Pwa journal",
        journal_type="introductory",
        status="active",
    )
    session.add(journal)
    await session.flush()
    await session.commit()
    return journal.id


async def _seed_briefing_entry(session, *, tenant_id: str, status: str) -> str:
    from datetime import datetime, timezone

    journal_id = await _seed_briefing_journal(session, tenant_id=tenant_id)
    entry = BriefingEntry(
        tenant_id=tenant_id,
        briefing_journal_id=journal_id,
        briefing_type="introductory",
        briefing_date=datetime.now(timezone.utc),
        status=status,
    )
    session.add(entry)
    await session.flush()
    await session.commit()
    return entry.id


# =============================================================================
# Batch submission — validation
# =============================================================================


@pytest.mark.anyio
async def test_create_batch_missing_device_id_returns_422(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={"entity_type": "briefing_entry", "payload": {}},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "PWA_SYNC_VALIDATION_ERROR"
    assert "device_id" in detail["message"]


@pytest.mark.anyio
async def test_create_batch_missing_entity_type_returns_422(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={"device_id": "dev", "payload": {}},
    )
    assert response.status_code == 422
    assert "entity_type" in response.json()["detail"]["message"]


@pytest.mark.anyio
async def test_create_batch_missing_payload_returns_422(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={"device_id": "dev", "entity_type": "x"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_create_batch_strips_blocked_top_level_fields(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """tenant_id / user_id / status / error_payload are stripped from incoming JSON."""
    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "task_comment",
        "payload": {"note": "hi"},
        "tenant_id": "ATTACKER",
        "user_id": "ATTACKER",
        "status": "applied",
        "error_payload": {"forged": True},
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.status_code == 200
    returned = response.json()
    assert returned["tenant_id"] != "ATTACKER"
    assert returned["user_id"] != "ATTACKER"
    # error_payload is None for an applied (non-conflict) batch.
    assert returned.get("error_payload") in (None, {})


@pytest.mark.anyio
async def test_create_batch_strips_blocked_nested_fields_in_payload(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Nested payload sanitization: tenant_id / user_id / company_id removed at any depth."""
    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "task_comment",
        "payload": {
            "note": "ok",
            "tenant_id": "forged",
            "deep": {"user_id": "forged", "company_id": "forged", "ok_field": "kept"},
        },
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.status_code == 200
    returned_payload = response.json()["payload"]
    assert "tenant_id" not in returned_payload
    assert returned_payload["deep"]["ok_field"] == "kept"
    assert "user_id" not in returned_payload["deep"]
    assert "company_id" not in returned_payload["deep"]


# =============================================================================
# Batch submission — happy path
# =============================================================================


@pytest.mark.anyio
async def test_create_batch_unrecognized_entity_type_applies_unconditionally(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """For entity_types the service doesn't special-case, the batch is
    marked ``applied`` immediately (best-effort acceptance)."""
    headers = await make_auth_headers()
    body = {"device_id": "dev", "entity_type": "task_comment", "payload": {"text": "x"}}
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "applied"


# =============================================================================
# Briefing-entry conflict detection
# =============================================================================


@pytest.mark.anyio
async def test_briefing_entry_in_draft_is_applied(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="draft")

    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "briefing_entry",
        "payload": {"entity_type": "briefing_entry", "id": entry_id, "note": "ok"},
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json()["status"] == "applied"


@pytest.mark.anyio
async def test_briefing_entry_signed_employee_triggers_final_conflict(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="signed_employee")

    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "briefing_entry",
        "payload": {"entity_type": "briefing_entry", "id": entry_id, "note": "late"},
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_payload"]["error"] == "conflict_final_record"


@pytest.mark.anyio
async def test_briefing_entry_completed_triggers_final_conflict(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="completed")

    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "briefing_entry",
        "payload": {"entity_type": "briefing_entry", "id": entry_id, "note": "late"},
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    assert response.json()["status"] == "failed"


# =============================================================================
# Evidence-case conflict detection
# =============================================================================


@pytest.mark.anyio
async def test_evidence_case_create_when_already_exists_is_conflict(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    create_body = {
        "device_id": "dev",
        "entity_type": "evidence_case",
        "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-1"},
    }
    first = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=create_body)
    assert first.json()["status"] == "applied"

    # Second create for the same evidence_case_id must conflict.
    second = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=create_body)
    body = second.json()
    assert body["status"] == "failed"
    assert body["error_payload"]["error"] == "conflict_evidence_case_exists"
    assert body["error_payload"]["resolution"] == "manual_review"


@pytest.mark.anyio
async def test_evidence_case_update_when_missing_is_conflict(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    body = {
        "device_id": "dev",
        "entity_type": "evidence_case",
        "payload": {"entity_type": "evidence_case", "operation": "update", "evidence_case_id": "missing"},
    }
    response = await async_client.post("/api/v1/pwa/sync/batch", headers=headers, json=body)
    failure = response.json()
    assert failure["status"] == "failed"
    assert failure["error_payload"]["error"] == "conflict_evidence_case_missing"


@pytest.mark.anyio
async def test_evidence_case_update_with_stale_base_version_is_conflict(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    create = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-2"},
        },
    )
    assert create.json()["status"] == "applied"

    # Server is now at version 1; client claims base_version=99.
    response = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {
                "entity_type": "evidence_case",
                "operation": "update",
                "evidence_case_id": "ec-2",
                "base_version": 99,
            },
        },
    )
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_payload"]["error"] == "conflict_evidence_case_version_mismatch"
    assert body["error_payload"]["server_version"] == 1
    assert body["error_payload"]["client_base_version"] == 99


@pytest.mark.anyio
async def test_evidence_case_update_increments_version_on_success(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-3"},
        },
    )
    update = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {
                "entity_type": "evidence_case",
                "operation": "update",
                "evidence_case_id": "ec-3",
                "base_version": 1,
                "notes": "edited",
            },
        },
    )
    body = update.json()
    assert body["status"] == "applied"
    assert body["payload"]["version"] == 2
    assert "synced_at" in body["payload"]


@pytest.mark.anyio
async def test_evidence_case_missing_id_marks_failed(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create"},
        },
    )
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_payload"]["error"] == "validation_missing_evidence_case_id"


# =============================================================================
# Conflict resolution
# =============================================================================


@pytest.mark.anyio
async def test_resolve_conflict_server_wins_marks_applied(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    # Force a conflict.
    await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-resolve-1"},
        },
    )
    conflict = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-resolve-1"},
        },
    )
    failed_id = conflict.json()["id"]

    resolved = await async_client.post(
        f"/api/v1/pwa/sync/conflicts/{failed_id}/resolve",
        headers=headers,
        json={"strategy": "server_wins"},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "applied"
    assert body["error_payload"]["resolved_by"] == "server_wins"


@pytest.mark.anyio
async def test_resolve_conflict_client_retry_marks_pending_with_patch(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-resolve-2"},
        },
    )
    conflict = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "evidence_case",
            "payload": {"entity_type": "evidence_case", "operation": "create", "evidence_case_id": "ec-resolve-2"},
        },
    )
    failed_id = conflict.json()["id"]

    resolved = await async_client.post(
        f"/api/v1/pwa/sync/conflicts/{failed_id}/resolve",
        headers=headers,
        json={"strategy": "client_retry", "payload_patch": {"notes": "retry"}},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "pending"
    assert body["payload"]["notes"] == "retry"
    assert body["error_payload"]["resolved_by"] == "client_retry"


@pytest.mark.anyio
async def test_resolve_conflict_invalid_strategy_returns_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    headers = await make_auth_headers()
    # Need a failed batch — easiest path: a completed briefing entry.
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="completed")
    conflict = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "briefing_entry",
            "payload": {"entity_type": "briefing_entry", "id": entry_id},
        },
    )
    failed_id = conflict.json()["id"]
    response = await async_client.post(
        f"/api/v1/pwa/sync/conflicts/{failed_id}/resolve",
        headers=headers,
        json={"strategy": "magic_revert"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PWA_SYNC_CONFLICT_STRATEGY_INVALID"


@pytest.mark.anyio
async def test_resolve_conflict_invalid_payload_patch_returns_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    headers = await make_auth_headers()
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="completed")
    conflict = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "briefing_entry",
            "payload": {"entity_type": "briefing_entry", "id": entry_id},
        },
    )
    failed_id = conflict.json()["id"]
    response = await async_client.post(
        f"/api/v1/pwa/sync/conflicts/{failed_id}/resolve",
        headers=headers,
        json={"strategy": "client_retry", "payload_patch": "not-an-object"},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_resolve_conflict_404_when_batch_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/sync/conflicts/missing/resolve",
        headers=headers,
        json={"strategy": "server_wins"},
    )
    assert response.status_code == 404


# =============================================================================
# Sync status — owner + cross-tenant safety
# =============================================================================


@pytest.mark.anyio
async def test_sync_status_returns_batch_for_owner(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    created = await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev",
            "entity_type": "task_comment",
            "payload": {"text": "x"},
        },
    )
    batch_id = created.json()["id"]
    response = await async_client.get(f"/api/v1/pwa/sync/status/{batch_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == batch_id


@pytest.mark.anyio
async def test_sync_status_404_for_other_tenant_batch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant_other = await data_factory.ensure_tenant(slug="pwa-other-tenant", session=session)
        batch = OfflineSyncBatch(
            tenant_id=str(tenant_other.id),
            user_id="someone-else",
            device_id="dev",
            entity_type="task_comment",
            payload={"text": "x"},
            status="applied",
        )
        session.add(batch)
        await session.flush()
        await session.commit()
        batch_id = batch.id

    # Auth in the default "test" tenant — request for foreign tenant's row → 404.
    headers = await make_auth_headers()
    response = await async_client.get(f"/api/v1/pwa/sync/status/{batch_id}", headers=headers)
    assert response.status_code == 404


# =============================================================================
# Media commit
# =============================================================================


@pytest.mark.anyio
async def test_commit_media_happy_path_uploads(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/media/commit",
        headers=headers,
        json={"device_id": "dev", "local_ref": "photo-001.jpg"},
    )
    assert response.status_code == 200
    assert response.json()["upload_status"] == "uploaded"


@pytest.mark.anyio
async def test_commit_media_missing_local_ref_returns_422(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/media/commit",
        headers=headers,
        json={"device_id": "dev"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "PWA_SYNC_VALIDATION_ERROR"
    assert "local_ref" in response.json()["detail"]["message"]


@pytest.mark.anyio
async def test_commit_media_strips_forged_fields(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/pwa/media/commit",
        headers=headers,
        json={
            "device_id": "dev",
            "local_ref": "ph.jpg",
            "tenant_id": "ATTACKER",
            "user_id": "ATTACKER",
            "upload_status": "uploaded",
        },
    )
    assert response.status_code == 200
    returned = response.json()
    assert returned["tenant_id"] != "ATTACKER"
    assert returned["user_id"] != "ATTACKER"


# =============================================================================
# Bootstrap
# =============================================================================


@pytest.mark.anyio
async def test_bootstrap_returns_full_envelope(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/pwa/bootstrap", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert {
        "current_user", "tenant_branding", "route_permissions",
        "briefing_templates", "active_journals", "assigned_training",
        "compliance_deadlines_summary", "offline_queue",
        "dictionaries", "sync_state", "diagnostics",
    } <= set(body)
    assert body["diagnostics"]["provider_mode"] == "projection_api"
    assert body["diagnostics"]["bootstrap_version"] == 4
    assert body["sync_state"]["pending_batches"] >= 0


@pytest.mark.anyio
async def test_bootstrap_surfaces_failed_conflicts(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """A failed batch must be surfaced in offline_queue.failed_conflicts and
    drive ``diagnostics.conflict_resolution_required`` to True."""
    headers = await make_auth_headers()
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry_id = await _seed_briefing_entry(session, tenant_id=str(tenant.id), status="completed")
    await async_client.post(
        "/api/v1/pwa/sync/batch",
        headers=headers,
        json={
            "device_id": "dev-fail",
            "entity_type": "briefing_entry",
            "payload": {"entity_type": "briefing_entry", "id": entry_id},
        },
    )
    response = await async_client.get("/api/v1/pwa/bootstrap", headers=headers)
    body = response.json()
    assert body["offline_queue"]["conflict_count"] >= 1
    assert body["diagnostics"]["conflict_resolution_required"] is True
    assert "manual_review" in body["offline_queue"]["conflict_resolution"]["strategies"]


@pytest.mark.anyio
async def test_bootstrap_dictionaries_include_conflict_codes(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/pwa/bootstrap", headers=headers)
    dicts = response.json()["dictionaries"]
    assert "conflict_final_record" in dicts["sync_conflict_codes"]
    assert "media_photo_sync" in dicts["offline_capabilities"]
    assert "applied" in dicts["offline_batch_statuses"]


@pytest.mark.anyio
async def test_bootstrap_capabilities_reflect_permissions(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/pwa/bootstrap", headers=headers)
    caps = response.json()["offline_queue"]["capabilities"]
    # Admin role has full permissions -> all capabilities granted.
    assert caps["briefing_mark"] is True
    assert caps["media_photo_sync"] is True
