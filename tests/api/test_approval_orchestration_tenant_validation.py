"""Тенант-валидация user_id, записываемых роутером approval-orchestration.

user.id глобален (не тенант-скоупен): user_id/escalation_user_id шага маршрута
и target_user_id делегирования обязаны ссылаться на пользователя текущего
тенанта — зеркало валидации approval-signing v1 / Task.assignee_id
(save-time 422, execution-time fail-closed 409 для легаси-строк).
"""

from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import (
    ApprovalInstanceStep,
    ApprovalRoute,
    ApprovalRouteStatus,
    ApprovalRouteStep,
    RoleEnum,
)

_BASE = "/api/v1"


def _route_payload(code: str) -> dict:
    return {"code": code, "name": f"Orch route {code}", "status": "active"}


def _step_payload(user_id: str | None = None, escalation_user_id: str | None = None) -> dict:
    payload: dict = {"order_no": 1, "step_type": "approve"}
    if user_id is not None:
        payload["user_id"] = user_id
    if escalation_user_id is not None:
        payload["escalation_user_id"] = escalation_user_id
    return payload


async def _create_route(async_client, headers, code: str) -> str:
    response = await async_client.post(
        f"{_BASE}/approval-routes", json=_route_payload(code), headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    return response.json()["id"]


async def _seed_own_and_foreign_users(sessionmaker, data_factory, *, suffix: str):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        own_user = await data_factory.create_user(
            tenant=tenant,
            email=f"own-orch-{suffix}@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        foreign_tenant = await data_factory.ensure_tenant(
            slug=f"foreign-orch-{suffix}", session=session
        )
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email=f"foreign-orch-{suffix}@example.com", session=session
        )
        own_id, foreign_id = own_user.id, foreign_user.id
        await session.commit()
    return own_id, foreign_id


@pytest.mark.anyio
async def test_step_create_rejects_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    _, foreign_id = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="sc")
    route_id = await _create_route(async_client, headers, "STEP_CREATE_PIN")

    response = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=foreign_id),
        headers=headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_ORCHESTRATION_VALIDATION_ERROR"

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(ApprovalRouteStep).where(ApprovalRouteStep.approval_route_id == route_id)
                )
            )
            .scalars()
            .all()
        )
        assert rows == []


@pytest.mark.anyio
async def test_step_create_rejects_escalation_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    own_id, foreign_id = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="se")
    route_id = await _create_route(async_client, headers, "STEP_ESC_PIN")

    response = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=own_id, escalation_user_id=foreign_id),
        headers=headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_ORCHESTRATION_VALIDATION_ERROR"


@pytest.mark.anyio
async def test_step_create_accepts_users_from_own_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    own_id, _ = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="sk")
    route_id = await _create_route(async_client, headers, "STEP_OK_PIN")

    response = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=own_id, escalation_user_id=own_id),
        headers=headers,
    )
    assert response.status_code == status.HTTP_200_OK

    async with sessionmaker() as session:
        row = await session.get(ApprovalRouteStep, response.json()["id"])
        assert row.user_id == own_id
        assert row.escalation_user_id == own_id


@pytest.mark.anyio
async def test_step_patch_rejects_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    own_id, foreign_id = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="sp")
    route_id = await _create_route(async_client, headers, "STEP_PATCH_PIN")

    created = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=own_id),
        headers=headers,
    )
    assert created.status_code == status.HTTP_200_OK
    step_id = created.json()["id"]

    response = await async_client.patch(
        f"{_BASE}/approval-routes/{route_id}/steps/{step_id}",
        json=_step_payload(user_id=foreign_id),
        headers=headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_ORCHESTRATION_VALIDATION_ERROR"

    async with sessionmaker() as session:
        row = await session.get(ApprovalRouteStep, step_id)
        assert row.user_id == own_id


async def _start_instance_for_document(
    async_client, sessionmaker, data_factory, headers, *, route_id: str
) -> str:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        version_id = version.id
        await session.commit()
    started = await async_client.post(
        f"{_BASE}/approvals/start",
        json={
            "entity_type": "document",
            "entity_id": version_id,
            "approval_route_id": route_id,
        },
        headers=headers,
    )
    assert started.status_code == status.HTTP_200_OK
    return started.json()["id"]


@pytest.mark.anyio
async def test_delegate_rejects_target_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    own_id, foreign_id = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="dx")
    route_id = await _create_route(async_client, headers, "DELEGATE_PIN")
    created = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=own_id),
        headers=headers,
    )
    assert created.status_code == status.HTTP_200_OK
    instance_id = await _start_instance_for_document(
        async_client, sessionmaker, data_factory, headers, route_id=route_id
    )

    response = await async_client.post(
        f"{_BASE}/approvals/{instance_id}/delegate",
        json={"target_user_id": foreign_id},
        headers={**headers, "X-User-Id": own_id},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    async with sessionmaker() as session:
        step = (
            (
                await session.execute(
                    select(ApprovalInstanceStep).where(
                        ApprovalInstanceStep.approval_instance_id == instance_id
                    )
                )
            )
            .scalars()
            .one()
        )
        assert step.assignee_user_id == own_id


@pytest.mark.anyio
async def test_delegate_accepts_target_user_from_own_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    own_id, _ = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="dk")
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        delegatee = await data_factory.create_user(
            tenant=tenant,
            email="delegatee-orch-own@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        delegatee_id = delegatee.id
        await session.commit()
    route_id = await _create_route(async_client, headers, "DELEGATE_OK_PIN")
    created = await async_client.post(
        f"{_BASE}/approval-routes/{route_id}/steps",
        json=_step_payload(user_id=own_id),
        headers=headers,
    )
    assert created.status_code == status.HTTP_200_OK
    instance_id = await _start_instance_for_document(
        async_client, sessionmaker, data_factory, headers, route_id=route_id
    )

    response = await async_client.post(
        f"{_BASE}/approvals/{instance_id}/delegate",
        json={"target_user_id": delegatee_id},
        headers={**headers, "X-User-Id": own_id},
    )
    assert response.status_code == status.HTTP_200_OK

    async with sessionmaker() as session:
        step = (
            (
                await session.execute(
                    select(ApprovalInstanceStep).where(
                        ApprovalInstanceStep.approval_instance_id == instance_id
                    )
                )
            )
            .scalars()
            .one()
        )
        assert step.assignee_user_id == delegatee_id
        assert step.delegated_from_user_id == own_id


@pytest.mark.anyio
async def test_start_fails_closed_on_legacy_step_with_foreign_user(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Шаг маршрута, сохранённый до валидации (сеем напрямую в БД), не должен
    материализоваться в ApprovalInstanceStep на чужого пользователя: честный 409."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    _, foreign_id = await _seed_own_and_foreign_users(sessionmaker, data_factory, suffix="ls")
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        route = ApprovalRoute(
            tenant_id=str(tenant.id),
            code="LEGACY_ORCH_FOREIGN",
            name="Legacy orch route",
            status=ApprovalRouteStatus.ACTIVE,
        )
        session.add(route)
        await session.flush()
        session.add(
            ApprovalRouteStep(
                tenant_id=str(tenant.id),
                approval_route_id=route.id,
                order_no=1,
                step_type="approve",
                user_id=foreign_id,
            )
        )
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        route_id, version_id = route.id, version.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals/start",
        json={
            "entity_type": "document",
            "entity_id": version_id,
            "approval_route_id": route_id,
        },
        headers=headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT

    async with sessionmaker() as session:
        foreign_steps = (
            (
                await session.execute(
                    select(ApprovalInstanceStep).where(
                        ApprovalInstanceStep.assignee_user_id == foreign_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert foreign_steps == []
