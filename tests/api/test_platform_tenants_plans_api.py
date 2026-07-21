"""HTTP contract for subscription plans on the managing-tenant fleet API.

A plan is the subscription product: applying it must (1) unlock exactly the tier's
features for that tenant and lock the rest, (2) set the tier's quota preset, and (3) be
derivable back from the tenant's feature set when the fleet is listed.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

BASE = "/api/v1/platform/tenants"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Make the default test tenant ("test") the managing tenant."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _provision(async_client: AsyncClient, headers, slug: str) -> str:
    response = await async_client.post(
        BASE,
        json={
            "slug": slug,
            "name": f"Компания {slug}",
            "owner_email": f"owner@{slug}.ru",
            "owner_password": "OwnerPass123",
            "kind": "customer",
            "demo_data": False,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["tenant"]["id"]


def _fleet_item(body: dict, tenant_id: str) -> dict:
    return next(item for item in body["items"] if item["tenant"]["id"] == tenant_id)


@pytest.mark.anyio
async def test_plan_catalog_lists_tiers_and_features(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get(f"{BASE}/plans", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    codes = {plan["code"] for plan in body["plans"]}
    assert codes == {"free", "pro", "enterprise"}
    feature_codes = {f["code"] for f in body["features"]}
    assert {"budget", "committees", "warehouse"} <= feature_codes
    pro = next(p for p in body["plans"] if p["code"] == "pro")
    assert "budget" in pro["feature_codes"]
    assert pro["quotas"]["max_doc_generations_per_month"] == 5000


@pytest.mark.anyio
async def test_plan_catalog_forbidden_for_non_admin(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get(f"{BASE}/plans", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_apply_plan_toggles_features_and_quotas(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "plantoggle")

    response = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "pro"}, headers=headers
    )

    assert response.status_code == 200, response.text
    item = response.json()
    assert item["plan"] == "pro"
    on = {f["code"] for f in item["features"] if f["on"]}
    # pro unlocks these...
    assert {"committees", "contractors", "medical", "report_builder", "budget", "sout"} == on
    # ...and leaves the enterprise-only ones locked.
    assert "rules_engine" not in on
    assert "warehouse" not in on
    assert item["quotas"]["max_doc_generations_per_month"] == 5000
    assert item["quotas"]["max_storage_mb"] == 20480


@pytest.mark.anyio
async def test_apply_plan_is_derivable_from_fleet_list(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """After applying a tier, the fleet listing reports that same tier back."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "planlist")

    await async_client.patch(f"{BASE}/{tenant_id}/plan", json={"plan": "free"}, headers=headers)
    listing = await async_client.get(BASE, headers=headers)
    assert listing.status_code == 200
    assert _fleet_item(listing.json(), tenant_id)["plan"] == "free"

    # Upgrading swaps the whole set — the derived code must follow.
    await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "enterprise"}, headers=headers
    )
    listing = await async_client.get(BASE, headers=headers)
    upgraded = _fleet_item(listing.json(), tenant_id)
    assert upgraded["plan"] == "enterprise"
    assert all(feature["on"] for feature in upgraded["features"])


@pytest.mark.anyio
async def test_apply_unknown_plan_is_422(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    tenant_id = await _provision(async_client, headers, "planbad")

    response = await async_client.patch(
        f"{BASE}/{tenant_id}/plan", json={"plan": "platinum"}, headers=headers
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_apply_plan_unknown_tenant_is_404(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.patch(
        f"{BASE}/does-not-exist/plan", json={"plan": "pro"}, headers=headers
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_apply_plan_forbidden_for_non_managing_tenant(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    async with sessionmaker() as session:
        outsider = await data_factory.ensure_tenant(slug="planoutsider", session=session)
        await session.commit()
        outsider_id = outsider.id
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="planoutsider", email="admin@planoutsider.ru"
    )

    response = await async_client.patch(
        f"{BASE}/{outsider_id}/plan", json={"plan": "pro"}, headers=headers
    )

    assert response.status_code == 403
