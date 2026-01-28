from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.file import File, FileKind, FileScanStatus
from app.models.models import Outbox, RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_training_api_flow(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        tenant_id = str(tenant.id)
        file = File(
            tenant_id=tenant.id,
            storage_key="certificates/sample.pdf",
            bucket="test",
            sha256="0" * 64,
            size=128,
            mime="application/pdf",
            kind=FileKind.DOCUMENT,
            scan_status=FileScanStatus.CLEAN,
        )
        session.add(file)
        await session.commit()
        await session.refresh(file)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    course_payload = {
        "title": "Safety Basics",
        "code": "SAFE-1",
        "description": "Intro safety course",
        "valid_period_days": 365,
    }
    course_response = await async_client.post(
        "/api/v1/training/courses", json=course_payload, headers=headers
    )
    assert course_response.status_code == status.HTTP_201_CREATED
    course = course_response.json()

    plan_payload = {
        "company_id": company.id,
        "course_id": course["id"],
        "person_id": person.id,
        "is_mandatory": True,
        "due_date": str(date.today() + timedelta(days=30)),
    }
    plan_response = await async_client.post(
        "/api/v1/training/plans", json=plan_payload, headers=headers
    )
    assert plan_response.status_code == status.HTTP_201_CREATED
    plan = plan_response.json()

    session_payload = {
        "person_id": person.id,
        "course_id": course["id"],
        "plan_id": plan["id"],
        "status": "completed",
        "score": 95,
        "notes": "Passed on first attempt",
    }
    training_session_response = await async_client.post(
        "/api/v1/training/sessions", json=session_payload, headers=headers
    )
    assert training_session_response.status_code == status.HTTP_201_CREATED
    training_session = training_session_response.json()

    async with sessionmaker() as session:
        assigned_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "TrainingAssigned",
                )
            )
        ).scalar_one_or_none()
        assert assigned_entry is not None
        assert assigned_entry.payload["training_event_id"] == plan["id"]

        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "TrainingCompleted",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["training_event_id"] == training_session["id"]

    certificate_payload = {
        "person_id": person.id,
        "course_id": course["id"],
        "plan_id": plan["id"],
        "session_id": training_session["id"],
        "file_id": file.id,
        "number": "CERT-001",
        "issued_at": str(date.today()),
        "valid_until": str(date.today() + timedelta(days=365)),
    }
    certificate_response = await async_client.post(
        "/api/v1/training/certificates", json=certificate_payload, headers=headers
    )
    assert certificate_response.status_code == status.HTTP_201_CREATED

    expiring_response = await async_client.get(
        "/api/v1/training/certificates/expiring?within_days=365", headers=headers
    )
    assert expiring_response.status_code == status.HTTP_200_OK
    expiring_payload = expiring_response.json()
    assert expiring_payload["total"] >= 1
