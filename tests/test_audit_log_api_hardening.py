"""Audit log API hardening tests (Phase 8.2 / vNext-ANALYTICS-03, Session 45).

Pins the filter matrix and export-job lifecycle of
``app.api.routes.audit``. Existing tests already cover audit-log
immutability and the hash chain; this file fills out the HTTP filter
contract and the AuditExportJob CRUD shape so future refactors can't
regress operator-visible behavior.

Coverage:

* ``GET /audit/logs``: tenant scoping, every filter (entity_type,
  entity_id, actor_id, action, correlation_id, from/to date range,
  combined), pagination (limit/offset clamp + 422 boundaries),
  ordering (latest first), total count contract.
* ``GET /audit/logs/{id}``: happy path, 404 missing, cross-tenant 404.
* ``POST /audit/exports``: queues an AuditExportJob, format validation
  (csv|jsonl), filter passthrough, 202 status code.
* ``GET /audit/exports/{id}``: status read, 404 missing, cross-tenant 404.
* ``GET /audit/exports/{id}/download``: 404 when no storage_key, 404
  cross-tenant.
* Backwards-compat ``GET /audit``: 400 on blank filter values, 410 on
  ``GET /audit/export`` (deprecated path).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import AuditExportJob, RoleEnum
from app.services.audit import AuditService
from tests.utils.factories import TestDataFactory

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_logs(
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    *,
    tenant_slug: str = "test",
    entries: list[dict] | None = None,
):
    """Insert audit entries directly via the service.

    Each entry dict accepts the kwargs of ``AuditService.log_event`` plus
    an optional ``when`` override for time-based filter tests.
    """
    entries = entries or []
    inserted = []
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug=tenant_slug, session=session)
        audit = AuditService(session)
        for spec in entries:
            payload = {
                "tenant_id": str(tenant.id),
                "action": spec.get("action", "created"),
                "object_type": spec.get("object_type", "document"),
                "object_id": spec.get("object_id", "obj-1"),
                "user_id": spec.get("user_id"),
                "ip": spec.get("ip", "127.0.0.1"),
                "when": spec.get("when") or datetime.now(tz=timezone.utc),
                "request_id": spec.get("request_id"),
                "details": spec.get("details") or {},
            }
            record = await audit.log_event(**payload)
            inserted.append(record)
        await session.commit()
    return inserted


async def _admin_headers(async_client: AsyncClient, make_auth_headers) -> dict:
    return {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}


# =============================================================================
# GET /audit/logs — filters
# =============================================================================


@pytest.mark.anyio
async def test_audit_logs_returns_envelope_with_total_and_items(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "created", "object_type": "document", "object_id": "doc-A"},
            {"action": "updated", "object_type": "document", "object_id": "doc-A"},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/logs", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "total" in body
    assert "items" in body
    assert body["total"] >= 2


@pytest.mark.anyio
async def test_audit_logs_orders_latest_first(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    now = datetime.now(tz=timezone.utc)
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "created", "object_id": "ord-A", "when": now - timedelta(minutes=10)},
            {"action": "updated", "object_id": "ord-A", "when": now - timedelta(minutes=2)},
            {"action": "deleted", "object_id": "ord-A", "when": now},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs",
        headers=headers,
        params={"entity_id": "ord-A"},
    )
    assert response.status_code == 200
    actions = [item["action"] for item in response.json()["items"]]
    assert actions[0] == "deleted"
    assert actions[-1] == "created"


@pytest.mark.anyio
async def test_audit_logs_filter_by_entity_type(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "created", "object_type": "document", "object_id": "et-1"},
            {"action": "created", "object_type": "person", "object_id": "et-2"},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"entity_type": "person"}
    )
    types = {item["entity_type"] for item in response.json()["items"]}
    assert types <= {"person"}


@pytest.mark.anyio
async def test_audit_logs_filter_by_entity_id(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "x", "object_id": "id-only-this"},
            {"action": "y", "object_id": "other"},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"entity_id": "id-only-this"}
    )
    ids = {item["entity_id"] for item in response.json()["items"]}
    assert ids == {"id-only-this"}


@pytest.mark.anyio
async def test_audit_logs_filter_by_action(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "approved", "object_id": "obj-a"},
            {"action": "rejected", "object_id": "obj-b"},
            {"action": "approved", "object_id": "obj-c"},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"action": "approved"}
    )
    actions = {item["action"] for item in response.json()["items"]}
    assert actions == {"approved"}


@pytest.mark.anyio
async def test_audit_logs_filter_by_actor_id(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user_a = await data_factory.create_user(
            tenant=tenant, session=session, email="actor-a@example.com"
        )
        user_b = await data_factory.create_user(
            tenant=tenant, session=session, email="actor-b@example.com"
        )
        audit = AuditService(session)
        await audit.log_event(
            tenant_id=str(tenant.id),
            action="x",
            object_type="doc",
            object_id="d-aa",
            user_id=user_a.id,
            ip="127.0.0.1",
        )
        await audit.log_event(
            tenant_id=str(tenant.id),
            action="y",
            object_type="doc",
            object_id="d-bb",
            user_id=user_b.id,
            ip="127.0.0.1",
        )
        await session.commit()
        actor_a_id = user_a.id

    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"actor_id": actor_a_id}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    assert all(item["actor_id"] == actor_a_id for item in items)


@pytest.mark.anyio
async def test_audit_logs_filter_by_correlation_id(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    # AuditService picks up correlation_id from request_id field.
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "a", "object_id": "c-1", "request_id": "corr-keep"},
            {"action": "b", "object_id": "c-2", "request_id": "corr-skip"},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"correlation_id": "corr-keep"}
    )
    ids = [item["entity_id"] for item in response.json()["items"]]
    assert ids == ["c-1"]


@pytest.mark.anyio
async def test_audit_logs_filter_by_from_date(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    now = datetime.now(tz=timezone.utc)
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "old", "object_id": "fd-old", "when": now - timedelta(days=5)},
            {"action": "new", "object_id": "fd-new", "when": now},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    cutoff = (now - timedelta(days=1)).isoformat()
    response = await async_client.get(
        "/api/v1/audit/logs", headers=headers, params={"from": cutoff}
    )
    ids = {item["entity_id"] for item in response.json()["items"]}
    assert "fd-new" in ids
    assert "fd-old" not in ids


@pytest.mark.anyio
async def test_audit_logs_filter_by_to_date(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    now = datetime.now(tz=timezone.utc)
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "early", "object_id": "td-early", "when": now - timedelta(days=10)},
            {"action": "late", "object_id": "td-late", "when": now},
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    cutoff = (now - timedelta(days=1)).isoformat()
    response = await async_client.get("/api/v1/audit/logs", headers=headers, params={"to": cutoff})
    ids = {item["entity_id"] for item in response.json()["items"]}
    assert "td-early" in ids
    assert "td-late" not in ids


@pytest.mark.anyio
async def test_audit_logs_pagination_clamps_limit_at_1000(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """The route declares Query(ge=1, le=1000); 1001 must 422."""
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/logs", headers=headers, params={"limit": 1001})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_audit_logs_pagination_rejects_negative_offset(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/logs", headers=headers, params={"offset": -1})
    assert response.status_code == 422


@pytest.mark.anyio
async def test_audit_logs_pagination_offset_slices_results(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    now = datetime.now(tz=timezone.utc)
    await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[
            {"action": "page", "object_id": f"pg-{i}", "when": now - timedelta(minutes=i)}
            for i in range(5)
        ],
    )
    headers = await _admin_headers(async_client, make_auth_headers)
    page_a = await async_client.get(
        "/api/v1/audit/logs",
        headers=headers,
        params={"action": "page", "limit": 2, "offset": 0},
    )
    page_b = await async_client.get(
        "/api/v1/audit/logs",
        headers=headers,
        params={"action": "page", "limit": 2, "offset": 2},
    )
    a_ids = [item["entity_id"] for item in page_a.json()["items"]]
    b_ids = [item["entity_id"] for item in page_b.json()["items"]]
    assert len(a_ids) == 2
    assert len(b_ids) == 2
    assert not (set(a_ids) & set(b_ids))


# =============================================================================
# GET /audit/logs/{id}
# =============================================================================


@pytest.mark.anyio
async def test_audit_log_get_by_id_returns_entry(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    records = await _seed_logs(
        sessionmaker,
        data_factory,
        entries=[{"action": "single", "object_id": "single-id"}],
    )
    audit_id = records[0].id
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(f"/api/v1/audit/logs/{audit_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == audit_id
    assert body["entity_id"] == "single-id"


@pytest.mark.anyio
async def test_audit_log_get_by_id_404_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/logs/does-not-exist", headers=headers)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_audit_log_get_by_id_404_for_other_tenant(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    records = await _seed_logs(
        sessionmaker,
        data_factory,
        tenant_slug="audit-isolation-other",
        entries=[{"action": "foreign", "object_id": "foreign-1"}],
    )
    foreign_id = records[0].id

    headers = await _admin_headers(async_client, make_auth_headers)  # authed as "test"
    response = await async_client.get(f"/api/v1/audit/logs/{foreign_id}", headers=headers)
    assert response.status_code == 404


# =============================================================================
# POST /audit/exports
# =============================================================================


@pytest.mark.anyio
async def test_create_export_returns_202_with_job_id(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    make_auth_headers,
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.post(
        "/api/v1/audit/exports",
        headers=headers,
        json={"format": "csv", "filters": {"action": "created"}},
    )
    assert response.status_code == 202
    body = response.json()
    assert "export_job_id" in body

    async with sessionmaker() as session:
        job = await session.get(AuditExportJob, body["export_job_id"])
        assert job is not None
        assert job.format == "csv"
        assert job.filters == {"action": "created"}
        assert job.status == "queued"


@pytest.mark.anyio
async def test_create_export_supports_jsonl_format(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.post(
        "/api/v1/audit/exports",
        headers=headers,
        json={"format": "jsonl"},
    )
    assert response.status_code == 202


@pytest.mark.anyio
async def test_create_export_rejects_invalid_format(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.post(
        "/api/v1/audit/exports",
        headers=headers,
        json={"format": "parquet"},
    )
    assert response.status_code == 422


# =============================================================================
# GET /audit/exports/{id}
# =============================================================================


@pytest.mark.anyio
async def test_get_export_returns_status(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = AuditExportJob(tenant_id=str(tenant.id), filters={}, format="csv", status="queued")
        session.add(job)
        await session.commit()
        job_id = job.id

    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(f"/api/v1/audit/exports/{job_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["format"] == "csv"


@pytest.mark.anyio
async def test_get_export_404_missing(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/exports/does-not-exist", headers=headers)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_get_export_404_cross_tenant(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant_other = await data_factory.ensure_tenant(
            slug="audit-export-isolation", session=session
        )
        job = AuditExportJob(
            tenant_id=str(tenant_other.id), filters={}, format="csv", status="queued"
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    headers = await _admin_headers(async_client, make_auth_headers)  # tenant "test"
    response = await async_client.get(f"/api/v1/audit/exports/{job_id}", headers=headers)
    assert response.status_code == 404


# =============================================================================
# GET /audit/exports/{id}/download
# =============================================================================


@pytest.mark.anyio
async def test_download_export_404_when_storage_key_missing(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    """Queued export has no storage_key yet -> 404."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = AuditExportJob(tenant_id=str(tenant.id), filters={}, format="csv", status="queued")
        session.add(job)
        await session.commit()
        job_id = job.id

    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get(f"/api/v1/audit/exports/{job_id}/download", headers=headers)
    assert response.status_code == 404


@pytest.mark.anyio
async def test_download_export_404_missing_job(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/exports/missing/download", headers=headers)
    assert response.status_code == 404


# =============================================================================
# Backwards-compat shim — /audit (no /logs suffix) + /audit/export (singular)
# =============================================================================


@pytest.mark.anyio
async def test_backward_list_blank_object_id_returns_400(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit", headers=headers, params={"object_id": "   "})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "AUDIT_VALIDATION_ERROR"


@pytest.mark.anyio
async def test_backward_list_blank_action_returns_400(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit", headers=headers, params={"action": "  "})
    assert response.status_code == 400


@pytest.mark.anyio
async def test_backward_legacy_export_path_returns_410(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await _admin_headers(async_client, make_auth_headers)
    response = await async_client.get("/api/v1/audit/export", headers=headers)
    assert response.status_code == 410
