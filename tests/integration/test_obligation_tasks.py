from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum, TrainingCourse
from app.models.obligations import Task, TaskPriority, TaskStatus


async def _create_course(session: AsyncSession, tenant_id: str) -> TrainingCourse:
    course = TrainingCourse(tenant_id=tenant_id, title="Safety Basics", code="SAFE-1")
    session.add(course)
    await session.flush()
    return course


@pytest.mark.anyio
async def test_training_assignment_creates_task(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        course = await _create_course(session, tenant.id)
        await session.commit()

    payload = {
        "company_id": company.id,
        "course_id": course.id,
        "person_id": person.id,
        "due_date": date.today().isoformat(),
        "is_mandatory": True,
    }
    response = await async_client.post("/api/v1/training/plans", json=payload, headers=headers)
    assert response.status_code == 201

    tasks_response = await async_client.get("/api/v1/tasks", headers=headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["items"]
    assert any(task["entity_type"] == "training_plan" for task in tasks)


@pytest.mark.anyio
async def test_medical_requirement_creates_task(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    payload = {"person_id": person.id, "due_date": date.today().isoformat()}
    response = await async_client.post(
        "/api/v1/medical/requirements", json=payload, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["entity_type"] == "medical_requirement"


@pytest.mark.anyio
async def test_inspection_creates_task(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()

    payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "Ростехнадзор",
        "scheduled_at": date.today().isoformat(),
    }
    response = await async_client.post("/api/v1/inspections", json=payload, headers=headers)
    assert response.status_code == 201

    tasks_response = await async_client.get("/api/v1/tasks?type=inspection", headers=headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["items"]
    assert any(task["entity_type"] == "inspection" for task in tasks)


@pytest.mark.anyio
async def test_attestation_creates_task(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    payload = {
        "person_id": person.id,
        "name": "Electrical safety",
        "expires_at": date.today().isoformat(),
    }
    response = await async_client.post("/api/v1/attestations", json=payload, headers=headers)
    assert response.status_code == 201

    tasks_response = await async_client.get("/api/v1/tasks?type=attestation", headers=headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["items"]
    assert any(task["entity_type"] == "attestation" for task in tasks)


@pytest.mark.anyio
async def test_overdue_filter(async_client, sessionmaker, data_factory, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        task = Task(
            tenant_id=tenant.id,
            title="Overdue task",
            due_at=datetime.now(timezone.utc) - timedelta(days=1),
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
        )
        session.add(task)
        await session.commit()

    response = await async_client.get("/api/v1/tasks?overdue=true", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == task.id for item in items)
