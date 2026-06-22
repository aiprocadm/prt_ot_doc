"""Пагинация журнала GET /sign/pep/requests: limit/offset, total, стабильная сортировка."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import PPEIssue, RoleEnum, SignatureRequest


async def _world_with_requests(
    async_client, sessionmaker, data_factory, make_auth_headers, *, count: int
):
    """Тенант + person + N ППЭ-выдач → N ПЭП-запросов через HTTP. Возвращает (headers, ids)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session, name="PEP PAGE")
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        issues = []
        for i in range(count):
            issue = PPEIssue(
                tenant_id=tenant.id,
                person_id=person.id,
                item_name=f"Каска page-{i}",
                quantity=1,
                status="issued",
            )
            session.add(issue)
            issues.append(issue)
        await session.commit()
        issue_ids = [issue.id for issue in issues]
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    created_ids = []
    for issue_id in issue_ids:
        resp = await async_client.post(
            "/api/v1/sign/pep/requests",
            json={
                "object_type": "ppe_issue",
                "object_id": issue_id,
                "purpose": "ppe_issue",
                "signer_person_id": person.id,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        created_ids.append(resp.json()["id"])
    return headers, created_ids


@pytest.mark.asyncio
async def test_journal_returns_total_and_respects_limit_offset(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers, ids = await _world_with_requests(
        async_client, sessionmaker, data_factory, make_auth_headers, count=3
    )

    # Без параметров: форма ответа прежняя (items) + новое поле total.
    full = await async_client.get("/api/v1/sign/pep/requests", headers=headers)
    assert full.status_code == 200, full.text
    body = full.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3

    page1 = await async_client.get(
        "/api/v1/sign/pep/requests", params={"limit": 2, "offset": 0}, headers=headers
    )
    assert page1.status_code == 200
    assert page1.json()["total"] == 3
    assert len(page1.json()["items"]) == 2

    page2 = await async_client.get(
        "/api/v1/sign/pep/requests", params={"limit": 2, "offset": 2}, headers=headers
    )
    assert page2.status_code == 200
    assert page2.json()["total"] == 3
    assert len(page2.json()["items"]) == 1

    # Страницы не пересекаются и в объединении дают весь журнал.
    ids_page1 = [item["id"] for item in page1.json()["items"]]
    ids_page2 = [item["id"] for item in page2.json()["items"]]
    assert not set(ids_page1) & set(ids_page2)
    assert set(ids_page1) | set(ids_page2) == set(ids)


@pytest.mark.asyncio
async def test_journal_stable_sort_created_desc_id_desc(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers, ids = await _world_with_requests(
        async_client, sessionmaker, data_factory, make_auth_headers, count=3
    )
    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(SignatureRequest).where(SignatureRequest.id.in_(ids))))
            .scalars()
            .all()
        )
    expected = [row.id for row in sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True)]
    listed = await async_client.get("/api/v1/sign/pep/requests", headers=headers)
    got = [item["id"] for item in listed.json()["items"] if item["id"] in set(ids)]
    assert got == expected


@pytest.mark.asyncio
async def test_journal_total_respects_filters(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers, ids = await _world_with_requests(
        async_client, sessionmaker, data_factory, make_auth_headers, count=2
    )
    async with sessionmaker() as session:
        row = (
            await session.execute(select(SignatureRequest).where(SignatureRequest.id == ids[0]))
        ).scalar_one()
        object_id = row.object_id
    filtered = await async_client.get(
        "/api/v1/sign/pep/requests",
        params={"object_type": "ppe_issue", "object_id": object_id},
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert [item["id"] for item in filtered.json()["items"]] == [ids[0]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 201}, {"offset": -1}],
    ids=["limit-zero", "limit-over-max", "offset-negative"],
)
async def test_journal_pagination_validation_422(
    async_client, sessionmaker, data_factory, make_auth_headers, params
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    resp = await async_client.get("/api/v1/sign/pep/requests", params=params, headers=headers)
    assert resp.status_code == 422, resp.text
