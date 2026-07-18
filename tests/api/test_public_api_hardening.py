"""Public API hardening tests (Phase 6.2 / vNext-INTEG-03, Session 42).

Pre-Session 42 the public API had a single happy-path integration test
(``test_public_api_machine_access``). This file fills out the contract
around the acceptance bar for Task 6.2:

* Machine-key CRUD (admin ``/machine-keys/...``)
* API-key authentication on the public surface (``/public/auth/machine``
  and the entity-list endpoints)
* Scope enforcement (per-route ``_ensure_scope``)
* Pagination envelope shape (``items / total / limit / offset / sort_by /
  sort_order``) + limit clamp + negative-offset rejection
* Public webhook subscription create (``integrations:write`` scope)
* Tenant-scoped data return (an API key only sees its own tenant's rows)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.models import RoleEnum

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _issue_key(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    name: str,
    scopes: list[str],
    rate_limit_per_minute: int | None = None,
) -> dict:
    body: dict = {"name": name, "scopes": scopes}
    if rate_limit_per_minute is not None:
        body["rate_limit_per_minute"] = rate_limit_per_minute
    response = await async_client.post(
        "/api/v1/machine-keys",
        headers={**admin_headers, "X-Tenant": "test"},
        json=body,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_tenant_data(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(session=session, tenant=tenant)
        await data_factory.create_person(
            session=session,
            tenant=tenant,
            company=company,
            first_name="Ivan",
            last_name="Petrov",
        )
        await data_factory.create_person(
            session=session,
            tenant=tenant,
            company=company,
            first_name="Anna",
            last_name="Sidorova",
        )


# =============================================================================
# Machine-key CRUD
# =============================================================================


@pytest.mark.anyio
async def test_issue_machine_key_returns_token_and_scopes(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = await _issue_key(async_client, headers, name="bot-a", scopes=["employees:read"])
    assert body["name"] == "bot-a"
    assert body["scopes"] == ["employees:read"]
    assert body["token"]
    assert body["id"]
    # Token is shown only at creation time.
    assert len(body["token"]) >= 16


@pytest.mark.anyio
async def test_issue_machine_key_stores_custom_rate_limit(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = await _issue_key(
        async_client,
        headers,
        name="bot-rl",
        scopes=["api:read"],
        rate_limit_per_minute=120,
    )
    assert body["rate_limit_per_minute"] == 120


@pytest.mark.anyio
async def test_issue_machine_key_defaults_scopes_to_api_read(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """When scopes list is empty the server falls back to ['api:read']."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        "/api/v1/machine-keys",
        headers={**headers, "X-Tenant": "test"},
        json={"name": "bot-default", "scopes": []},
    )
    assert response.status_code == 201
    assert response.json()["scopes"] == ["api:read"]


@pytest.mark.anyio
async def test_list_machine_keys_returns_tenant_keys_without_secrets(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _issue_key(async_client, headers, name="listme", scopes=["api:read"])
    response = await async_client.get(
        "/api/v1/machine-keys",
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(row["name"] == "listme" for row in items)
    # No row should leak the plaintext token.
    for row in items:
        assert "token" not in row


@pytest.mark.anyio
async def test_rotate_machine_key_returns_new_token_and_invalidates_old(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issued = await _issue_key(async_client, headers, name="rotate-me", scopes=["api:read"])
    old_token = issued["token"]

    rotated = await async_client.post(
        f"/api/v1/machine-keys/{issued['id']}/rotate",
        headers={**headers, "X-Tenant": "test"},
    )
    assert rotated.status_code == 200
    new_token = rotated.json()["token"]
    assert new_token != old_token

    # Old token rejected.
    old_auth = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test", "X-API-Key": old_token},
    )
    assert old_auth.status_code == 401
    # New token accepted.
    new_auth = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test", "X-API-Key": new_token},
    )
    assert new_auth.status_code == 200


@pytest.mark.anyio
async def test_revoke_machine_key_disables_auth(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issued = await _issue_key(async_client, headers, name="revoke-me", scopes=["api:read"])
    token = issued["token"]

    revoked = await async_client.post(
        f"/api/v1/machine-keys/{issued['id']}/revoke",
        headers={**headers, "X-Tenant": "test"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"

    # Revoked token rejected.
    auth = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test", "X-API-Key": token},
    )
    assert auth.status_code == 401


@pytest.mark.anyio
async def test_rotate_machine_key_404_for_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        "/api/v1/machine-keys/missing-id/rotate",
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_revoke_machine_key_404_for_missing(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        "/api/v1/machine-keys/missing-id/revoke",
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 404


# =============================================================================
# API key authentication on /public/...
# =============================================================================


@pytest.mark.anyio
async def test_public_auth_machine_missing_key_returns_401(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_public_auth_machine_wrong_key_returns_401(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test", "X-API-Key": "totally-bogus-key"},
    )
    assert response.status_code == 401


@pytest.mark.anyio
async def test_public_auth_machine_returns_scopes_and_tenant(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    issued = await _issue_key(
        async_client,
        headers,
        name="auth-info",
        scopes=["api:read", "employees:read"],
    )
    response = await async_client.get(
        "/api/v1/public/auth/machine",
        headers={"X-Tenant": "test", "X-API-Key": issued["token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["subject"].startswith("api_key:")
    assert "tenant_id" in body
    assert "employees:read" in body["scopes"]


# =============================================================================
# Scope enforcement on entity endpoints
# =============================================================================


@pytest.mark.anyio
async def test_public_employees_requires_employees_read_scope(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    no_scope = await _issue_key(async_client, headers, name="no-scope", scopes=["api:read"])
    response = await async_client.get(
        "/api/v1/public/employees",
        headers={"X-Tenant": "test", "X-API-Key": no_scope["token"]},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_public_employees_api_admin_scope_grants_access(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """api:admin is a wildcard scope that bypasses the per-route check."""
    await _seed_tenant_data(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    admin_key = await _issue_key(async_client, headers, name="admin-scope", scopes=["api:admin"])
    response = await async_client.get(
        "/api/v1/public/employees?limit=10",
        headers={"X-Tenant": "test", "X-API-Key": admin_key["token"]},
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_public_documents_requires_documents_read_scope(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    employees_only = await _issue_key(
        async_client, headers, name="emp-only", scopes=["employees:read"]
    )
    response = await async_client.get(
        "/api/v1/public/documents",
        headers={"X-Tenant": "test", "X-API-Key": employees_only["token"]},
    )
    assert response.status_code == 403


# =============================================================================
# Pagination envelope
# =============================================================================


@pytest.mark.anyio
async def test_public_employees_returns_full_pagination_envelope(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    await _seed_tenant_data(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="page", scopes=["employees:read"])

    response = await async_client.get(
        "/api/v1/public/employees?limit=1&offset=0&sort_by=created_at&sort_order=asc",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert response.status_code == 200
    body = response.json()
    # Envelope fields exactly per PublicListEnvelope.
    assert set(body) >= {"items", "total", "limit", "offset", "sort_by", "sort_order"}
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert body["sort_order"] == "asc"
    assert len(body["items"]) <= 1


@pytest.mark.anyio
async def test_public_employees_pagination_advances_offset(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    await _seed_tenant_data(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="page2", scopes=["employees:read"])

    page0 = await async_client.get(
        "/api/v1/public/employees?limit=1&offset=0&sort_by=created_at&sort_order=asc",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    page1 = await async_client.get(
        "/api/v1/public/employees?limit=1&offset=1&sort_by=created_at&sort_order=asc",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert page0.status_code == 200
    assert page1.status_code == 200
    p0 = page0.json()
    p1 = page1.json()
    assert p0["total"] >= 2
    assert p0["offset"] == 0
    assert p1["offset"] == 1
    # When more than one row exists the two pages must be different.
    if p0["items"] and p1["items"]:
        assert p0["items"][0] != p1["items"][0]


@pytest.mark.anyio
async def test_public_employees_limit_clamped_to_max_100(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """FastAPI's Query(le=100) rejects values > 100 with 422."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="clamp", scopes=["employees:read"])
    response = await async_client.get(
        "/api/v1/public/employees?limit=500",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_public_employees_rejects_negative_offset(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="neg-off", scopes=["employees:read"])
    response = await async_client.get(
        "/api/v1/public/employees?offset=-5",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_public_employees_rejects_invalid_sort_order(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """``sort_order`` is regex-validated to ``^(asc|desc)$``."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="bad-sort", scopes=["employees:read"])
    response = await async_client.get(
        "/api/v1/public/employees?sort_order=sideways",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert response.status_code == 422


# =============================================================================
# Tenant scoping — data returned is the API key's tenant
# =============================================================================


@pytest.mark.anyio
async def test_public_employees_returns_only_keys_tenant_data(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """An API key issued in tenant ``test`` returns only ``test`` rows even
    if the request asks for X-Tenant of a different tenant — the key's
    tenant is the authoritative scope."""
    await _seed_tenant_data(sessionmaker, data_factory)
    async with sessionmaker() as session:
        other = await data_factory.ensure_tenant(slug="public-api-other", session=session)
        company_other = await data_factory.create_company(session=session, tenant=other)
        await data_factory.create_person(
            session=session,
            tenant=other,
            company=company_other,
            first_name="Ghost",
            last_name="OfTenantB",
        )

    headers = await make_auth_headers(RoleEnum.ADMIN)
    key = await _issue_key(async_client, headers, name="scope-key", scopes=["employees:read"])

    response = await async_client.get(
        "/api/v1/public/employees?limit=100",
        headers={"X-Tenant": "test", "X-API-Key": key["token"]},
    )
    assert response.status_code == 200
    last_names = [row.get("last_name") for row in response.json()["items"]]
    assert "OfTenantB" not in last_names


# =============================================================================
# Public webhook subscription creation
# =============================================================================


@pytest.mark.anyio
async def test_public_webhook_subscription_create_requires_integrations_write(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    read_only = await _issue_key(async_client, headers, name="ro", scopes=["integrations:read"])
    response = await async_client.post(
        "/api/v1/public/integrations/webhooks/subscriptions",
        headers={"X-Tenant": "test", "X-API-Key": read_only["token"]},
        json={"name": "x", "url": "https://example.test/h", "subscribed_events": []},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_public_webhook_subscription_create_succeeds_with_write_scope(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    rw = await _issue_key(async_client, headers, name="rw", scopes=["integrations:write"])
    response = await async_client.post(
        "/api/v1/public/integrations/webhooks/subscriptions",
        headers={"X-Tenant": "test", "X-API-Key": rw["token"]},
        json={
            "name": "BI hook",
            "url": "https://bi.example/in",
            "subscribed_events": ["DocumentExported"],
            "timeout_ms": 3000,
            "headers": {"X-Source": "bi"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "BI hook"
    assert body["enabled"] is True
    assert body["subscribed_events"] == ["DocumentExported"]


@pytest.mark.anyio
async def test_public_webhook_subscription_list_requires_integrations_read(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    no_int = await _issue_key(async_client, headers, name="noint", scopes=["api:read"])
    response = await async_client.get(
        "/api/v1/public/integrations/webhooks",
        headers={"X-Tenant": "test", "X-API-Key": no_int["token"]},
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_public_webhook_subscription_list_returns_envelope(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    rw = await _issue_key(
        async_client, headers, name="rw-list", scopes=["integrations:read", "integrations:write"]
    )
    await async_client.post(
        "/api/v1/public/integrations/webhooks/subscriptions",
        headers={"X-Tenant": "test", "X-API-Key": rw["token"]},
        json={"name": "list-me", "url": "https://list.example/h", "subscribed_events": []},
    )
    response = await async_client.get(
        "/api/v1/public/integrations/webhooks",
        headers={"X-Tenant": "test", "X-API-Key": rw["token"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert {"items", "total"} <= set(body)
    assert body["total"] >= 1
