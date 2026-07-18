"""API contract: /budget — flag gate, RBAC, CRUD, seed, overview/breakdown, ETag (§12.4 Task 6)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/budget"

BUDGET = {
    "name": "Обучение 2026",
    "domain": "training",
    "period_start": "2026-01-01",
    "period_end": "2026-12-31",
    "planned_amount": 100000,
}


async def _enable_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool = True) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "budget"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="budget", title="Бюджет ОТ")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=on))
        await session.commit()
        return str(tenant.id)


async def _seed_training_article_id(async_client: AsyncClient, headers: dict[str, str]) -> str:
    seeded = await async_client.post(f"{BASE}/articles/seed-defaults", headers=headers)
    assert seeded.status_code == status.HTTP_200_OK, seeded.text
    articles = await async_client.get(f"{BASE}/articles", headers=headers)
    assert articles.status_code == status.HTTP_200_OK, articles.text
    return next(a["id"] for a in articles.json()["items"] if a["code"] == "training_external")


@pytest.mark.asyncio
async def test_flag_off_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/budgets", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # default-off, без FeatureEnablement
    assert "is not enabled" in resp.text


@pytest.mark.asyncio
async def test_budgets_crud_e2e(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(f"{BASE}/budgets", json=BUDGET, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    budget_id = created.json()["id"]

    lst = await async_client.get(f"{BASE}/budgets", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1
    assert lst.json()["items"][0]["id"] == budget_id

    article_id = await _seed_training_article_id(async_client, headers)

    with_article = await async_client.post(
        f"{BASE}/expenses",
        json={
            "domain": "training",
            "article_id": article_id,
            "title": "Курс УЦ",
            "occurred_on": "2026-03-10",
            "amount": 1000,
        },
        headers=headers,
    )
    assert with_article.status_code == status.HTTP_201_CREATED, with_article.text
    assert with_article.json()["article_name"] == "Обучение в учебном центре"
    without_article = await async_client.post(
        f"{BASE}/expenses",
        json={
            "domain": "training",
            "title": "Раздатка",
            "occurred_on": "2026-04-01",
            "amount": 500,
        },
        headers=headers,
    )
    assert without_article.status_code == status.HTTP_201_CREATED, without_article.text
    assert without_article.json()["article_name"] is None

    detail = await async_client.get(f"{BASE}/budgets/{budget_id}", headers=headers)
    assert detail.status_code == status.HTTP_200_OK, detail.text
    body = detail.json()
    assert body["actual_total"] == 1500.0
    assert body["remaining"] == 98500.0
    assert body["expense_count"] == 2
    assert len(body["by_article"]) == 2
    assert any(r["article_name"] == "— без статьи" for r in body["by_article"])

    patched = await async_client.patch(
        f"{BASE}/budgets/{budget_id}", json={"planned_amount": 200000}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["planned_amount"] == 200000

    deleted = await async_client.delete(f"{BASE}/budgets/{budget_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"{BASE}/budgets/{budget_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_seed_defaults_idempotent_and_code_conflict(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    first = await async_client.post(f"{BASE}/articles/seed-defaults", headers=headers)
    assert first.status_code == status.HTTP_200_OK, first.text
    assert first.json() == {"created": 9, "skipped": 0}
    second = await async_client.post(f"{BASE}/articles/seed-defaults", headers=headers)
    assert second.status_code == status.HTTP_200_OK
    assert second.json() == {"created": 0, "skipped": 9}

    dup = await async_client.post(
        f"{BASE}/articles",
        json={"code": "other", "name": "Прочее (дубль)"},
        headers=headers,
    )
    assert dup.status_code == status.HTTP_409_CONFLICT
    assert "ARTICLE_CODE_EXISTS" in dup.text


@pytest.mark.asyncio
async def test_expense_foreign_tenant_site_422(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-budget", session=session)
        foreign_site = await data_factory.create_site(tenant=foreign_tenant, session=session)
        await session.commit()
        foreign_site_id = str(foreign_site.id)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    denied = await async_client.post(
        f"{BASE}/expenses",
        json={
            "domain": "training",
            "title": "Чужая площадка",
            "occurred_on": "2026-02-01",
            "amount": 100,
            "site_id": foreign_site_id,
        },
        headers=headers,
    )
    assert denied.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, denied.text
    assert "unknown_site" in denied.text


@pytest.mark.asyncio
async def test_overview(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.get(f"{BASE}/overview", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert len(body["domains"]) == 4
    ppe = next(d for d in body["domains"] if d["domain"] == "ppe")
    assert ppe["read_only"] is True
    assert all(d["read_only"] is False for d in body["domains"] if d["domain"] != "ppe")

    bad = await async_client.get(
        f"{BASE}/overview?date_from=2026-12-31&date_to=2026-01-01", headers=headers
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad.text
    assert "window_invalid" in bad.text


@pytest.mark.asyncio
async def test_breakdown(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    bad = await async_client.get(f"{BASE}/breakdown?dimension=nope", headers=headers)
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, bad.text
    assert "breakdown_dimension_unknown" in bad.text

    ok = await async_client.get(f"{BASE}/breakdown?dimension=article", headers=headers)
    assert ok.status_code == status.HTTP_200_OK, ok.text
    assert ok.json()["dimension"] == "article"


@pytest.mark.asyncio
async def test_rbac(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    accountant = await make_auth_headers(RoleEnum.ACCOUNTANT)
    assert (
        await async_client.get(f"{BASE}/budgets", headers=accountant)
    ).status_code == status.HTTP_200_OK
    lead = await make_auth_headers(RoleEnum.OT_PB_LEAD)
    assert (
        await async_client.get(f"{BASE}/budgets", headers=lead)
    ).status_code == status.HTTP_200_OK
    worker = await make_auth_headers(RoleEnum.WORKER)
    assert (
        await async_client.get(f"{BASE}/budgets", headers=worker)
    ).status_code == status.HTTP_403_FORBIDDEN
    denied_post = await async_client.post(f"{BASE}/budgets", json=BUDGET, headers=worker)
    assert denied_post.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_budgets_list_etag_304(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(f"{BASE}/budgets", json=BUDGET, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text

    lst = await async_client.get(f"{BASE}/budgets", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    etag = lst.headers.get("etag")
    assert etag
    not_modified = await async_client.get(
        f"{BASE}/budgets", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_budget_patch_explicit_null_422(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(f"{BASE}/budgets", json=BUDGET, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    budget_id = created.json()["id"]

    null_end = await async_client.patch(
        f"{BASE}/budgets/{budget_id}", json={"period_end": None}, headers=headers
    )
    assert null_end.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, null_end.text
    assert "invalid_field_null" in null_end.text


@pytest.mark.asyncio
async def test_static_paths_not_shadowed(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(f"{BASE}/budgets", json=BUDGET, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text

    articles = await async_client.get(f"{BASE}/articles", headers=headers)
    assert articles.status_code == status.HTTP_200_OK, articles.text
    overview = await async_client.get(f"{BASE}/overview", headers=headers)
    assert overview.status_code == status.HTTP_200_OK, overview.text
