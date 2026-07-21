"""API contract: /budget/reimbursements — флаг, RBAC, CRUD, состав, FSM, ETag (§12.4 срез-2).

Зеркало tests/api/test_budget_api.py для среза-1: сервисный слой покрыт в
test_budget_reimbursement_service.py, здесь — только то, что видно снаружи по HTTP
(коды ответов, маппинг ошибок в 404/409/422, порядок роутов, ETag/304).
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/budget"
CLAIMS = f"{BASE}/reimbursements"

CLAIM = {
    "title": "Возмещение СФР за I полугодие",
    "period_start": "2026-01-01",
    "period_end": "2026-06-30",
    "requested_amount": 50000,
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


async def _create_claim(client: AsyncClient, headers: dict[str, str], **overrides) -> str:
    resp = await client.post(CLAIMS, json={**CLAIM, **overrides}, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    return body["id"]


async def _create_expense(
    client: AsyncClient, headers: dict[str, str], *, amount: float = 1200, title: str = "Курс УЦ"
) -> str:
    resp = await client.post(
        f"{BASE}/expenses",
        json={
            "domain": "training",
            "title": title,
            "occurred_on": "2026-03-10",
            "amount": amount,
        },
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _submitted_claim(client: AsyncClient, headers: dict[str, str]) -> tuple[str, str]:
    """Заявка в статусе submitted + id привязанного расхода (правки уже запрещены)."""
    claim_id = await _create_claim(client, headers)
    expense_id = await _create_expense(client, headers)
    linked = await client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": expense_id}, headers=headers
    )
    assert linked.status_code == status.HTTP_201_CREATED, linked.text
    submitted = await client.post(f"{CLAIMS}/{claim_id}/submit", headers=headers)
    assert submitted.status_code == status.HTTP_200_OK, submitted.text
    assert submitted.json()["status"] == "submitted"
    return claim_id, expense_id


@pytest.mark.asyncio
async def test_flag_off_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(CLAIMS, headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # default-off, как у ядра бюджета
    assert "is not enabled" in resp.text


@pytest.mark.asyncio
async def test_rbac(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    for role in (RoleEnum.ADMIN, RoleEnum.ACCOUNTANT, RoleEnum.OT_PB_LEAD):
        allowed = await make_auth_headers(role)
        assert (await async_client.get(CLAIMS, headers=allowed)).status_code == status.HTTP_200_OK

    worker = await make_auth_headers(RoleEnum.WORKER)
    assert (await async_client.get(CLAIMS, headers=worker)).status_code == status.HTTP_403_FORBIDDEN
    denied_post = await async_client.post(CLAIMS, json=CLAIM, headers=worker)
    assert denied_post.status_code == status.HTTP_403_FORBIDDEN

    admin = await make_auth_headers(RoleEnum.ADMIN)
    claim_id = await _create_claim(async_client, admin)
    denied_action = await async_client.post(f"{CLAIMS}/{claim_id}/submit", headers=worker)
    assert denied_action.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_crud_and_items_e2e(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    claim_id = await _create_claim(async_client, headers)

    lst = await async_client.get(CLAIMS, headers=headers)
    assert lst.status_code == status.HTTP_200_OK, lst.text
    assert lst.json()["total"] == 1
    assert lst.json()["items"][0]["id"] == claim_id
    assert lst.json()["items"][0]["item_count"] == 0

    expense_id = await _create_expense(async_client, headers, amount=1200)
    linked = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": expense_id}, headers=headers
    )
    # Статический сегмент /items не должен перехватываться FSM-роутом /{action}.
    assert linked.status_code == status.HTTP_201_CREATED, linked.text
    assert linked.json() == {
        "expense_id": expense_id,
        "title": "Курс УЦ",
        "domain": "training",
        "occurred_on": "2026-03-10",
        "amount": 1200.0,
    }

    detail = await async_client.get(f"{CLAIMS}/{claim_id}", headers=headers)
    assert detail.status_code == status.HTTP_200_OK, detail.text
    body = detail.json()
    assert body["item_count"] == 1
    assert body["items_amount"] == 1200.0
    assert body["requested_amount"] == 50000.0  # сумма заявки не подменяется составом
    assert [item["expense_id"] for item in body["items"]] == [expense_id]

    patched = await async_client.patch(
        f"{CLAIMS}/{claim_id}", json={"requested_amount": 60000}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["requested_amount"] == 60000.0
    assert patched.json()["status"] == "draft"  # PATCH не трогает статус

    unlinked = await async_client.delete(f"{CLAIMS}/{claim_id}/items/{expense_id}", headers=headers)
    assert unlinked.status_code == status.HTTP_204_NO_CONTENT
    emptied = await async_client.get(f"{CLAIMS}/{claim_id}", headers=headers)
    assert emptied.json()["item_count"] == 0
    assert emptied.json()["items_amount"] == 0.0

    deleted = await async_client.delete(f"{CLAIMS}/{claim_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"{CLAIMS}/{claim_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND
    assert "REIMBURSEMENT_NOT_FOUND" in gone.text


@pytest.mark.asyncio
async def test_lifecycle_submit_approve_pay(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id, _ = await _submitted_claim(async_client, headers)

    submitted = await async_client.get(f"{CLAIMS}/{claim_id}", headers=headers)
    assert submitted.json()["submitted_at"] is not None

    approved = await async_client.post(
        f"{CLAIMS}/{claim_id}/approve",
        json={"approved_amount": 40000, "decision_reason": "Частично"},
        headers=headers,
    )
    assert approved.status_code == status.HTTP_200_OK, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_amount"] == 40000.0
    assert approved.json()["decided_at"] is not None

    paid = await async_client.post(f"{CLAIMS}/{claim_id}/pay", headers=headers)
    assert paid.status_code == status.HTTP_200_OK, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_at"] is not None


@pytest.mark.asyncio
async def test_approve_without_body_defaults_to_requested(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id, _ = await _submitted_claim(async_client, headers)

    approved = await async_client.post(f"{CLAIMS}/{claim_id}/approve", headers=headers)
    assert approved.status_code == status.HTTP_200_OK, approved.text
    assert approved.json()["approved_amount"] == 50000.0


@pytest.mark.asyncio
async def test_invalid_transition_409(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id = await _create_claim(async_client, headers)

    # draft -> approved запрещён (только draft -> submitted)
    conflict = await async_client.post(f"{CLAIMS}/{claim_id}/approve", headers=headers)
    assert conflict.status_code == status.HTTP_409_CONFLICT, conflict.text
    assert "REIMBURSEMENT_TRANSITION_INVALID" in conflict.text


@pytest.mark.asyncio
async def test_frozen_after_submit_409(async_client, make_auth_headers, sessionmaker, data_factory):
    """После подачи заявка — документ во внешнем органе: правка/состав/удаление закрыты."""
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id, expense_id = await _submitted_claim(async_client, headers)
    other_expense = await _create_expense(async_client, headers, title="Второй расход")

    patched = await async_client.patch(
        f"{CLAIMS}/{claim_id}", json={"title": "Новое имя"}, headers=headers
    )
    assert patched.status_code == status.HTTP_409_CONFLICT, patched.text

    added = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": other_expense}, headers=headers
    )
    assert added.status_code == status.HTTP_409_CONFLICT, added.text

    removed = await async_client.delete(f"{CLAIMS}/{claim_id}/items/{expense_id}", headers=headers)
    assert removed.status_code == status.HTTP_409_CONFLICT, removed.text

    deleted = await async_client.delete(f"{CLAIMS}/{claim_id}", headers=headers)
    assert deleted.status_code == status.HTTP_409_CONFLICT, deleted.text


@pytest.mark.asyncio
async def test_duplicate_item_409(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id = await _create_claim(async_client, headers)
    expense_id = await _create_expense(async_client, headers)

    first = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": expense_id}, headers=headers
    )
    assert first.status_code == status.HTTP_201_CREATED, first.text
    again = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": expense_id}, headers=headers
    )
    assert again.status_code == status.HTTP_409_CONFLICT, again.text
    assert "REIMBURSEMENT_EXPENSE_LINKED" in again.text


@pytest.mark.asyncio
async def test_validation_422_matrix(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id = await _create_claim(async_client, headers)

    unknown_expense = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": "no-such-expense"}, headers=headers
    )
    assert unknown_expense.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "unknown_expense" in unknown_expense.text

    not_linked = await async_client.delete(
        f"{CLAIMS}/{claim_id}/items/no-such-expense", headers=headers
    )
    assert not_linked.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "expense_not_linked" in not_linked.text

    unknown_action = await async_client.post(f"{CLAIMS}/{claim_id}/frobnicate", headers=headers)
    assert unknown_action.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "unknown_action" in unknown_action.text

    unknown_status = await async_client.get(f"{CLAIMS}?status=nope", headers=headers)
    assert unknown_status.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "unknown_status" in unknown_status.text

    explicit_null = await async_client.patch(
        f"{CLAIMS}/{claim_id}", json={"title": None}, headers=headers
    )
    assert explicit_null.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "invalid_field_null" in explicit_null.text

    bad_period = await async_client.patch(
        f"{CLAIMS}/{claim_id}", json={"period_end": "2025-01-01"}, headers=headers
    )
    assert bad_period.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "period_invalid" in bad_period.text

    empty_submit = await async_client.post(f"{CLAIMS}/{claim_id}/submit", headers=headers)
    assert empty_submit.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "reimbursement_empty" in empty_submit.text


@pytest.mark.asyncio
async def test_decision_validation_422(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    over_cap_claim, _ = await _submitted_claim(async_client, headers)
    over_cap = await async_client.post(
        f"{CLAIMS}/{over_cap_claim}/approve", json={"approved_amount": 99999}, headers=headers
    )
    assert over_cap.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, over_cap.text
    assert "approved_amount_invalid" in over_cap.text

    reject_claim, _ = await _submitted_claim(async_client, headers)
    no_reason = await async_client.post(f"{CLAIMS}/{reject_claim}/reject", headers=headers)
    assert no_reason.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, no_reason.text
    assert "decision_reason_required" in no_reason.text

    rejected = await async_client.post(
        f"{CLAIMS}/{reject_claim}/reject",
        json={"decision_reason": "Нет документов"},
        headers=headers,
    )
    assert rejected.status_code == status.HTTP_200_OK, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["decision_reason"] == "Нет документов"


@pytest.mark.asyncio
async def test_foreign_tenant_company_422(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        foreign_tenant = await data_factory.ensure_tenant(
            slug="foreign-reimbursement", session=session
        )
        foreign_company = await data_factory.create_company(tenant=foreign_tenant, session=session)
        await session.commit()
        foreign_company_id = str(foreign_company.id)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    denied = await async_client.post(
        CLAIMS, json={**CLAIM, "company_id": foreign_company_id}, headers=headers
    )
    assert denied.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, denied.text
    assert "unknown_company" in denied.text


@pytest.mark.asyncio
async def test_list_filter_and_etag_invalidated_by_item(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    """Состав не входит в (id, updated_at) заявки — привязка расхода обязана сбросить ETag."""
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    claim_id = await _create_claim(async_client, headers)

    lst = await async_client.get(CLAIMS, headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    etag = lst.headers.get("etag")
    assert etag
    replay = await async_client.get(CLAIMS, headers={**headers, "If-None-Match": etag})
    assert replay.status_code == status.HTTP_304_NOT_MODIFIED

    expense_id = await _create_expense(async_client, headers, amount=700)
    linked = await async_client.post(
        f"{CLAIMS}/{claim_id}/items", json={"expense_id": expense_id}, headers=headers
    )
    assert linked.status_code == status.HTTP_201_CREATED, linked.text

    fresh = await async_client.get(CLAIMS, headers={**headers, "If-None-Match": etag})
    assert fresh.status_code == status.HTTP_200_OK, fresh.text
    assert fresh.json()["items"][0]["item_count"] == 1
    assert fresh.json()["items"][0]["items_amount"] == 700.0

    # Фильтр по статусу: черновик виден, поданных ещё нет.
    drafts = await async_client.get(f"{CLAIMS}?status=draft", headers=headers)
    assert drafts.status_code == status.HTTP_200_OK
    assert drafts.json()["total"] == 1
    submitted_only = await async_client.get(f"{CLAIMS}?status=submitted", headers=headers)
    assert submitted_only.status_code == status.HTTP_200_OK
    assert submitted_only.json()["total"] == 0


@pytest.mark.asyncio
async def test_unknown_claim_404(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    for method, url in (
        ("get", f"{CLAIMS}/missing"),
        ("patch", f"{CLAIMS}/missing"),
        ("delete", f"{CLAIMS}/missing"),
    ):
        resp = await getattr(async_client, method)(
            url, **({"json": {"title": "x"}} if method == "patch" else {}), headers=headers
        )
        assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
        assert "REIMBURSEMENT_NOT_FOUND" in resp.text

    action = await async_client.post(f"{CLAIMS}/missing/submit", headers=headers)
    assert action.status_code == status.HTTP_404_NOT_FOUND, action.text
    item = await async_client.post(
        f"{CLAIMS}/missing/items", json={"expense_id": "whatever"}, headers=headers
    )
    assert item.status_code == status.HTTP_404_NOT_FOUND, item.text
