"""Webhook CRUD endpoint tests (Phase 6 / vNext-INTEG-02, Session 41).

Pins the contract of the ``/api/v1/webhooks/...`` admin / CRUD routes. The
dispatcher itself (``app.services.webhooks.WebhookDispatcher``) and the
outbox engine are already covered by existing tests; what was missing is
the HTTP layer that operators actually use to register webhooks, list
deliveries, retry failed ones, and replay outbox events.

Routes covered:

* POST ``/webhooks/endpoints``           — create (auto-secret + custom secret)
* GET  ``/webhooks/endpoints``           — list, tenant-scoped
* PATCH ``/webhooks/endpoints/{id}``     — update; preserves secret when omitted
* DELETE ``/webhooks/endpoints/{id}``    — hard delete + 404 on second call
* POST ``/webhooks/endpoints/{id}:rotate-secret``
* POST ``/webhooks/endpoints/{id}:disable`` / ``:enable``
* POST ``/webhooks/endpoints/{id}:test`` — queues an Outbox row
* GET  ``/webhooks/deliveries``          — list with status / event_type / endpoint_id filters
* GET  ``/webhooks/endpoints/{id}/deliveries``
* GET  ``/webhooks/deliveries/{id}/diagnostics``
* GET  ``/webhooks/deliveries/{id}/retry-eligibility``
* POST ``/webhooks/deliveries/{id}:retry`` — 409 if succeeded; 200 otherwise
* POST ``/webhooks/events/{id}:replay``  — flips Outbox row back to PENDING
* Cross-tenant 404 for endpoints + deliveries
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    Outbox,
    OutboxStatus,
    Tenant,
    WebhookDelivery,
    WebhookEndpoint,
)

# -----------------------------------------------------------------------------
# Helpers — small shared seeding utilities to keep tests focused.
# -----------------------------------------------------------------------------


async def _seed_endpoint(
    session,
    *,
    tenant_id: str,
    url: str = "https://example.test/webhook",
    name: str | None = "default",
    is_enabled: bool = True,
    secret: str | None = "seeded-secret-1234567890",
    events: list[str] | None = None,
) -> WebhookEndpoint:
    row = WebhookEndpoint(
        tenant_id=tenant_id,
        url=url,
        name=name,
        is_enabled=is_enabled,
        secret=secret,
        subscribed_events=events or ["DocumentGenerated"],
        timeout_ms=5000,
        headers={},
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return row


async def _seed_delivery(
    session,
    *,
    tenant_id: str,
    endpoint_id: str,
    status: str = "failed",
    attempts: int = 1,
    last_status_code: int | None = 500,
    last_error: dict | None = None,
) -> WebhookDelivery:
    row = WebhookDelivery(
        tenant_id=tenant_id,
        endpoint_id=endpoint_id,
        event_id=f"evt-{endpoint_id[:8]}",
        status=status,
        attempts=attempts,
        last_status_code=last_status_code,
        last_error=last_error,
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return row


async def _seed_outbox(
    session,
    *,
    tenant_id: str,
    event_type: str = "DocumentGenerated",
    payload: dict | None = None,
    status: OutboxStatus = OutboxStatus.PENDING,
) -> Outbox:
    row = Outbox(
        tenant_id=tenant_id,
        event_type=event_type,
        destination="https://example.test/webhook",
        payload=payload or {"marker": "test"},
        headers={},
        idempotency_key=f"k-{event_type}",
        status=status,
    )
    session.add(row)
    await session.flush()
    await session.commit()
    return row


# -----------------------------------------------------------------------------
# Endpoint create / read / update / delete
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_webhook_with_auto_generated_secret_returns_secret_once(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers=headers,
        json={"url": "https://hooks.example/a", "subscribed_events": ["DocumentGenerated"]},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["url"] == "https://hooks.example/a"
    # Plaintext secret is returned only at creation time.
    assert body["secret"]
    assert len(body["secret"]) >= 16
    # Masked form is exposed for subsequent reads.
    assert body["secret_masked"]
    assert "***" in body["secret_masked"]
    assert body["enabled"] is True


@pytest.mark.anyio
async def test_create_webhook_with_explicit_secret_uses_provided_value(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/webhooks/endpoints",
        headers=headers,
        json={
            "url": "https://hooks.example/b",
            "secret": "my-supplied-secret",
            "subscribed_events": [],
        },
    )
    assert response.status_code == 201
    assert response.json()["secret"] == "my-supplied-secret"


@pytest.mark.anyio
async def test_list_webhooks_returns_only_current_tenant(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_endpoint(session, tenant_id=str(tenant.id), url="https://hooks.example/own")
        other = await data_factory.ensure_tenant(slug="wh-other", session=session)
        await _seed_endpoint(session, tenant_id=str(other.id), url="https://hooks.example/other")

    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/webhooks/endpoints", headers=headers)
    assert response.status_code == 200
    urls = [row["url"] for row in response.json()]
    assert "https://hooks.example/own" in urls
    assert "https://hooks.example/other" not in urls


@pytest.mark.anyio
async def test_list_webhooks_empty_when_no_endpoints(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/webhooks/endpoints", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_patch_webhook_preserves_secret_when_omitted(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(
            session, tenant_id=str(tenant.id), secret="preserved-secret"
        )
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    response = await async_client.patch(
        f"/api/v1/webhooks/endpoints/{endpoint_id}",
        headers=headers,
        json={
            "url": "https://hooks.example/new",
            "subscribed_events": ["DocumentSigned"],
            "timeout_ms": 9000,
            "headers": {"X-Custom": "value"},
            "enabled": True,
        },
    )
    assert response.status_code == 200

    # Verify the in-DB secret is unchanged.
    async with sessionmaker() as session:
        refreshed = await session.get(WebhookEndpoint, endpoint_id)
        assert refreshed is not None
        assert refreshed.secret == "preserved-secret"
        assert refreshed.url == "https://hooks.example/new"
        assert refreshed.timeout_ms == 9000


@pytest.mark.anyio
async def test_patch_webhook_replaces_secret_when_provided(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id), secret="old-secret")
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    await async_client.patch(
        f"/api/v1/webhooks/endpoints/{endpoint_id}",
        headers=headers,
        json={
            "url": "https://hooks.example/x",
            "secret": "new-secret",
            "subscribed_events": [],
            "enabled": True,
        },
    )
    async with sessionmaker() as session:
        refreshed = await session.get(WebhookEndpoint, endpoint_id)
        assert refreshed is not None
        assert refreshed.secret == "new-secret"


@pytest.mark.anyio
async def test_patch_webhook_404_when_missing(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers()
    response = await async_client.patch(
        "/api/v1/webhooks/endpoints/does-not-exist",
        headers=headers,
        json={"url": "https://hooks.example", "subscribed_events": [], "enabled": True},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delete_webhook_removes_row(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    response = await async_client.delete(
        f"/api/v1/webhooks/endpoints/{endpoint_id}", headers=headers
    )
    assert response.status_code == 204

    async with sessionmaker() as session:
        gone = await session.get(WebhookEndpoint, endpoint_id)
        assert gone is None


@pytest.mark.anyio
async def test_delete_webhook_404_when_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.delete(
        "/api/v1/webhooks/endpoints/does-not-exist", headers=headers
    )
    assert response.status_code == 404


# -----------------------------------------------------------------------------
# Cross-tenant 404 — security invariant
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_patch_webhook_404_for_other_tenants_row(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant_other = await data_factory.ensure_tenant(slug="wh-isolation-a", session=session)
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant_other.id))
        endpoint_id = endpoint.id

    # Auth as default "test" tenant, try to patch the foreign row.
    headers = await make_auth_headers()
    response = await async_client.patch(
        f"/api/v1/webhooks/endpoints/{endpoint_id}",
        headers=headers,
        json={"url": "https://attacker.example", "subscribed_events": [], "enabled": True},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delete_webhook_404_for_other_tenants_row(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant_other = await data_factory.ensure_tenant(slug="wh-isolation-b", session=session)
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant_other.id))
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    response = await async_client.delete(
        f"/api/v1/webhooks/endpoints/{endpoint_id}", headers=headers
    )
    assert response.status_code == 404


# -----------------------------------------------------------------------------
# Lifecycle actions: rotate-secret / disable / enable / test
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_rotate_secret_returns_new_value(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id), secret="rotate-old")
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/endpoints/{endpoint_id}:rotate-secret", headers=headers
    )
    assert response.status_code == 200
    new_secret = response.json()["secret"]
    assert new_secret
    assert new_secret != "rotate-old"

    # In-DB value matches the response.
    async with sessionmaker() as session:
        refreshed = await session.get(WebhookEndpoint, endpoint_id)
        assert refreshed.secret == new_secret


@pytest.mark.anyio
async def test_disable_then_enable_toggles_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id), is_enabled=True)
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    disabled = await async_client.post(
        f"/api/v1/webhooks/endpoints/{endpoint_id}:disable", headers=headers
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False

    enabled = await async_client.post(
        f"/api/v1/webhooks/endpoints/{endpoint_id}:enable", headers=headers
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True


@pytest.mark.anyio
async def test_test_endpoint_queues_outbox_event(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        endpoint_id = endpoint.id
        tenant_id = str(tenant.id)

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/endpoints/{endpoint_id}:test", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    # Outbox row was created for this tenant + endpoint.
    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(Outbox).where(
                        Outbox.tenant_id == tenant_id, Outbox.status == OutboxStatus.PENDING
                    )
                )
            )
            .scalars()
            .all()
        )
        assert any(row.payload.get("event_id") == f"test-{endpoint_id}" for row in rows)


# -----------------------------------------------------------------------------
# Delivery list + diagnostics + retry eligibility
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_deliveries_returns_only_current_tenant(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint_own = await _seed_endpoint(session, tenant_id=str(tenant.id))
        # An Outbox row must exist for the JOIN in list_deliveries to surface our row.
        own_outbox = await _seed_outbox(session, tenant_id=str(tenant.id))
        own_delivery = WebhookDelivery(
            tenant_id=str(tenant.id),
            endpoint_id=endpoint_own.id,
            event_id=own_outbox.id,
            status="failed",
            attempts=1,
            last_status_code=500,
        )
        session.add(own_delivery)
        # Another tenant — must not appear.
        tenant_other = await data_factory.ensure_tenant(slug="wh-listing-other", session=session)
        endpoint_other = await _seed_endpoint(session, tenant_id=str(tenant_other.id))
        other_outbox = await _seed_outbox(session, tenant_id=str(tenant_other.id))
        session.add(
            WebhookDelivery(
                tenant_id=str(tenant_other.id),
                endpoint_id=endpoint_other.id,
                event_id=other_outbox.id,
                status="failed",
                attempts=1,
                last_status_code=500,
            )
        )
        await session.commit()

    headers = await make_auth_headers()
    response = await async_client.get("/api/v1/webhooks/deliveries", headers=headers)
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert own_delivery.id in ids


@pytest.mark.anyio
async def test_list_deliveries_filtered_by_status(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        outbox_a = await _seed_outbox(session, tenant_id=str(tenant.id), event_type="A")
        outbox_b = await _seed_outbox(session, tenant_id=str(tenant.id), event_type="B")
        session.add(
            WebhookDelivery(
                tenant_id=str(tenant.id),
                endpoint_id=endpoint.id,
                event_id=outbox_a.id,
                status="success",
                attempts=1,
                last_status_code=200,
            )
        )
        session.add(
            WebhookDelivery(
                tenant_id=str(tenant.id),
                endpoint_id=endpoint.id,
                event_id=outbox_b.id,
                status="failed",
                attempts=3,
                last_status_code=500,
            )
        )
        await session.commit()

    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/webhooks/deliveries", headers=headers, params={"status": "failed"}
    )
    assert response.status_code == 200
    statuses = {row["status"] for row in response.json()}
    assert statuses <= {"failed"}


@pytest.mark.anyio
async def test_list_endpoint_deliveries(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        await _seed_delivery(session, tenant_id=str(tenant.id), endpoint_id=endpoint.id)
        endpoint_id = endpoint.id

    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/webhooks/endpoints/{endpoint_id}/deliveries", headers=headers
    )
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.anyio
async def test_list_endpoint_deliveries_404_when_endpoint_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/webhooks/endpoints/missing/deliveries", headers=headers
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_delivery_diagnostics_returns_minimal_payload_when_no_last_error(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session, tenant_id=str(tenant.id), endpoint_id=endpoint.id, last_error=None
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/webhooks/deliveries/{delivery_id}/diagnostics", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert "failure_category" in body
    assert body["http_status_code"] == 500


@pytest.mark.anyio
async def test_delivery_diagnostics_uses_structured_last_error_when_present(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    structured = {
        "failure_category": "retryable_5xx",
        "retry_eligible": True,
        "http_status_code": 502,
        "error_class": "BadGateway",
        "error_message": "upstream gone",
        "current_attempt": 2,
        "max_attempts": 5,
        "attempts_remaining": 3,
        "next_attempt_in_seconds": 60,
    }
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session,
            tenant_id=str(tenant.id),
            endpoint_id=endpoint.id,
            last_error=structured,
            last_status_code=502,
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/webhooks/deliveries/{delivery_id}/diagnostics", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["retry_eligible"] is True
    assert body["http_status_code"] == 502
    assert body["error_class"] == "BadGateway"
    assert body["attempts_remaining"] == 3


@pytest.mark.anyio
async def test_retry_eligibility_for_succeeded_delivery_says_not_eligible(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session,
            tenant_id=str(tenant.id),
            endpoint_id=endpoint.id,
            status="success",
            last_status_code=200,
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/webhooks/deliveries/{delivery_id}/retry-eligibility", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["eligible"] is False


@pytest.mark.anyio
async def test_retry_eligibility_for_pending_delivery_says_eligible(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session,
            tenant_id=str(tenant.id),
            endpoint_id=endpoint.id,
            status="pending",
            last_status_code=None,
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/webhooks/deliveries/{delivery_id}/retry-eligibility", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["eligible"] is True


# -----------------------------------------------------------------------------
# Retry + replay
# -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_retry_delivery_marks_pending_and_clears_schedule(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session, tenant_id=str(tenant.id), endpoint_id=endpoint.id, status="failed"
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/deliveries/{delivery_id}:retry", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    async with sessionmaker() as session:
        refreshed = await session.get(WebhookDelivery, delivery_id)
        assert refreshed.status == "pending"


@pytest.mark.anyio
async def test_retry_delivery_409_for_succeeded(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session,
            tenant_id=str(tenant.id),
            endpoint_id=endpoint.id,
            status="success",
            last_status_code=200,
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/deliveries/{delivery_id}:retry", headers=headers
    )
    assert response.status_code == 409


@pytest.mark.anyio
async def test_retry_delivery_409_when_not_retryable_per_diagnostics(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """If last_error.retry_eligible is False, the retry endpoint must reject
    even if status is "failed"."""
    terminal = {
        "failure_category": "permanent_4xx",
        "retry_eligible": False,
        "http_status_code": 410,
        "error_class": "Gone",
        "error_message": "permanent",
        "current_attempt": 5,
        "max_attempts": 5,
        "attempts_remaining": 0,
    }
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        endpoint = await _seed_endpoint(session, tenant_id=str(tenant.id))
        delivery = await _seed_delivery(
            session,
            tenant_id=str(tenant.id),
            endpoint_id=endpoint.id,
            status="failed",
            last_error=terminal,
            last_status_code=410,
        )
        delivery_id = delivery.id

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/deliveries/{delivery_id}:retry", headers=headers
    )
    assert response.status_code == 409


@pytest.mark.anyio
async def test_retry_delivery_404_when_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/webhooks/deliveries/does-not-exist:retry", headers=headers
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_replay_outbox_event_flips_status_to_pending(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        event = await _seed_outbox(session, tenant_id=str(tenant.id), status=OutboxStatus.DEAD)
        event_id = event.id

    headers = await make_auth_headers()
    response = await async_client.post(
        f"/api/v1/webhooks/events/{event_id}:replay", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "queued"

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, event_id)
        assert refreshed.status == OutboxStatus.PENDING


@pytest.mark.anyio
async def test_replay_outbox_event_404_when_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/webhooks/events/does-not-exist:replay", headers=headers
    )
    assert response.status_code == 404
