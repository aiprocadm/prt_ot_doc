"""Тенант-валидация user_id, записываемых роутером approval-signing v1.

user.id глобален (не тенант-скоупен): user_id шага маршрута и to_user_id
делегирования обязаны ссылаться на пользователя текущего тенанта — зеркало
валидации Task.assignee_id / rules-engine (save-time 422, execution fail-closed).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import (
    ApprovalProcess,
    ApprovalProcessStatus,
    ApprovalRoute,
    ApprovalTask,
    ApprovalTaskStatus,
    RoleEnum,
)

_BASE = "/api/v1/v1"


def _route_payload(user_id: str, *, code: str = "TENANT_PIN") -> dict:
    return {
        "code": code,
        "name": "Tenant pin route",
        "conditions": {},
        "steps": [{"type": "user", "user_id": user_id}],
    }


@pytest.mark.anyio
async def test_route_create_rejects_step_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-appr-c", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-appr-create@example.com", session=session
        )
        foreign_id = foreign_user.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals/routes", json=_route_payload(foreign_id), headers=headers
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_SIGNING_VALIDATION_ERROR"


@pytest.mark.anyio
async def test_route_create_requires_user_id_for_user_step(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    payload = _route_payload("ignored", code="NO_USER_ID")
    payload["steps"] = [{"type": "user"}]
    response = await async_client.post(f"{_BASE}/approvals/routes", json=payload, headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_SIGNING_VALIDATION_ERROR"


@pytest.mark.anyio
async def test_route_create_accepts_step_user_from_own_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        own_user = await data_factory.create_user(
            tenant=tenant,
            email="own-appr-step@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        own_id = own_user.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals/routes", json=_route_payload(own_id, code="OWN_OK"), headers=headers
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["code"] == "OWN_OK"


@pytest.mark.anyio
async def test_route_patch_rejects_step_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        own_user = await data_factory.create_user(
            tenant=tenant,
            email="own-appr-patch@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-appr-p", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-appr-patch@example.com", session=session
        )
        own_id, foreign_id = own_user.id, foreign_user.id
        await session.commit()

    created = await async_client.post(
        f"{_BASE}/approvals/routes",
        json=_route_payload(own_id, code="PATCH_PIN"),
        headers=headers,
    )
    assert created.status_code == status.HTTP_200_OK
    route_id = created.json()["id"]

    response = await async_client.patch(
        f"{_BASE}/approvals/routes/{route_id}",
        json=_route_payload(foreign_id, code="PATCH_PIN"),
        headers=headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_SIGNING_VALIDATION_ERROR"

    async with sessionmaker() as session:
        row = await session.get(ApprovalRoute, route_id)
        assert row.steps == [{"type": "user", "user_id": own_id}]


async def _seed_open_task(sessionmaker, data_factory, *, approver_email: str, slug_suffix: str):
    """Маршрут + процесс + OPEN-задача на approver'а собственного тенанта."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        approver = await data_factory.create_user(
            tenant=tenant, email=approver_email, role=RoleEnum.EMPLOYEE, session=session
        )
        route = ApprovalRoute(
            tenant_id=str(tenant.id),
            code=f"DELEGATE_{slug_suffix}",
            name="Delegate pin route",
            conditions={},
            steps=[{"type": "user", "user_id": approver.id}],
            is_active=True,
            priority=0,
            version=1,
        )
        session.add(route)
        await session.flush()
        process = ApprovalProcess(
            tenant_id=str(tenant.id),
            object_type="document_version",
            object_id=str(uuid4()),
            route_id=route.id,
            status=ApprovalProcessStatus.IN_PROGRESS,
            current_step=0,
        )
        session.add(process)
        await session.flush()
        task = ApprovalTask(
            tenant_id=str(tenant.id),
            process_id=process.id,
            step_no=0,
            assignee_type="user",
            assignee_id=approver.id,
            status=ApprovalTaskStatus.OPEN,
        )
        session.add(task)
        await session.flush()
        approver_id, task_id, tenant_id = approver.id, task.id, str(tenant.id)
        await session.commit()
    return approver_id, task_id, tenant_id


@pytest.mark.anyio
async def test_delegate_rejects_user_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    approver_id, task_id, _ = await _seed_open_task(
        sessionmaker, data_factory, approver_email="approver-del-x@example.com", slug_suffix="X"
    )
    async with sessionmaker() as session:
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-appr-d", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-appr-delegate@example.com", session=session
        )
        foreign_id = foreign_user.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals/tasks/{task_id}:delegate",
        json={"to_user_id": foreign_id},
        headers={**headers, "X-User-Id": approver_id},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]["code"] == "APPROVAL_SIGNING_VALIDATION_ERROR"

    async with sessionmaker() as session:
        task = await session.get(ApprovalTask, task_id)
        assert task.status is ApprovalTaskStatus.OPEN
        foreign_tasks = (
            (
                await session.execute(
                    select(ApprovalTask).where(ApprovalTask.assignee_id == foreign_id)
                )
            )
            .scalars()
            .all()
        )
        assert foreign_tasks == []


@pytest.mark.anyio
async def test_delegate_accepts_user_from_own_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    approver_id, task_id, _ = await _seed_open_task(
        sessionmaker, data_factory, approver_email="approver-del-ok@example.com", slug_suffix="OK"
    )
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        delegatee = await data_factory.create_user(
            tenant=tenant,
            email="delegatee-own@example.com",
            role=RoleEnum.EMPLOYEE,
            session=session,
        )
        delegatee_id = delegatee.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals/tasks/{task_id}:delegate",
        json={"to_user_id": delegatee_id},
        headers={**headers, "X-User-Id": approver_id},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "delegated"

    async with sessionmaker() as session:
        new_task = await session.get(ApprovalTask, body["new_task_id"])
        assert new_task.assignee_id == delegatee_id


@pytest.mark.anyio
async def test_start_fails_closed_on_legacy_route_with_foreign_step_user(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Маршрут, сохранённый до валидации (сеем напрямую в БД), не должен
    материализовать задачу на чужого пользователя: честный 409 вместо записи."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-appr-s", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-appr-start@example.com", session=session
        )
        route = ApprovalRoute(
            tenant_id=str(tenant.id),
            code="LEGACY_FOREIGN",
            name="Legacy route with foreign step user",
            conditions={},
            steps=[{"type": "user", "user_id": foreign_user.id}],
            is_active=True,
            priority=100,
            version=1,
        )
        session.add(route)
        await session.flush()
        foreign_id = foreign_user.id
        await session.commit()

    response = await async_client.post(
        f"{_BASE}/approvals:start",
        json={"object_type": "document_version", "object_id": str(uuid4()), "context": {}},
        headers=headers,
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["detail"]["code"] == "APPROVAL_SIGNING_CONFLICT"

    async with sessionmaker() as session:
        foreign_tasks = (
            (
                await session.execute(
                    select(ApprovalTask).where(ApprovalTask.assignee_id == foreign_id)
                )
            )
            .scalars()
            .all()
        )
        assert foreign_tasks == []
