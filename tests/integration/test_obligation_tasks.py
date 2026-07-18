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
async def test_medical_exams_registry_returns_tenant_scoped_rows(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.HR)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        from app.models.models import MedicalExam

        session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=date.today(),
                valid_until=date.today() + timedelta(days=30),
                conclusion="fit",
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/medical/exams", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["person_id"] == person.id
    assert body["items"][0]["exam_type"] == "periodic"


@pytest.mark.anyio
async def test_inspection_creates_task(async_client, sessionmaker, data_factory, make_auth_headers):
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


@pytest.mark.anyio
async def test_create_task_rejects_assignee_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-tasks", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-task-assignee@example.com", session=session
        )
        await session.commit()

    payload = {"title": "Чужой исполнитель", "assignee_id": foreign_user.id}
    response = await async_client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 422
    assert "TASK_VALIDATION_ERROR" in response.text


@pytest.mark.anyio
async def test_create_task_accepts_assignee_from_own_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        assignee = await data_factory.create_user(
            tenant=tenant,
            email="own-task-assignee@example.com",
            role=RoleEnum.WORKER,
            session=session,
        )
        await session.commit()

    payload = {"title": "Свой исполнитель", "assignee_id": assignee.id}
    response = await async_client.post("/api/v1/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    assert response.json()["assignee_id"] == assignee.id


@pytest.mark.anyio
async def test_update_task_rejects_assignee_from_another_tenant(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        foreign_tenant = await data_factory.ensure_tenant(slug="foreign-tasks-upd", session=session)
        foreign_user = await data_factory.create_user(
            tenant=foreign_tenant, email="foreign-task-upd@example.com", session=session
        )
        task = Task(
            tenant_id=tenant.id,
            title="Task to reassign",
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
        )
        session.add(task)
        await session.commit()

    response = await async_client.patch(
        f"/api/v1/tasks/{task.id}", json={"assignee_id": foreign_user.id}, headers=headers
    )
    assert response.status_code == 422
    assert "TASK_VALIDATION_ERROR" in response.text


@pytest.mark.anyio
async def test_priority_filter(async_client, sessionmaker, data_factory, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        critical_task = Task(
            tenant_id=tenant.id,
            title="Critical task",
            status=TaskStatus.OPEN,
            priority=TaskPriority.CRITICAL,
        )
        low_task = Task(
            tenant_id=tenant.id,
            title="Low task",
            status=TaskStatus.OPEN,
            priority=TaskPriority.LOW,
        )
        session.add_all([critical_task, low_task])
        await session.commit()

    response = await async_client.get("/api/v1/tasks?priority=critical", headers=headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["id"] == critical_task.id for item in items)
    assert all(item["id"] != low_task.id for item in items)
