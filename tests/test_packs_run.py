from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    MedicalExam,
    Person,
    PipelineRun,
    PipelineRunStatus,
    PPEIssue,
    Site,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
    Training,
    TrainingStatus,
)


async def _prepare_pack_environment(
    session,
    *,
    tenant_slug: str = "test",
    pack_code: str = "OT_ENTER_SITE",
    persons_count: int = 1,
    items_count: int = 1,
    training_valid: bool = True,
    medical_valid: bool = True,
    ppe_valid: bool = True,
) -> SimpleNamespace:
    tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one()
    session.info["tenant"] = tenant.slug

    company = Company(
        tenant_id=tenant.id,
        name="Acme LLC",
        inn="7701000000",
        legal_address="HQ",
        actual_address="HQ Block B",
        work_types=["Site entry"],
        hazardous_factors=["Noise"],
        phone_numbers=["+7 495 000-00-00"],
    )
    session.add(company)
    await session.flush()

    site = Site(
        tenant_id=tenant.id,
        company_id=company.id,
        name="Main",
        address="Zone A",
    )
    session.add(site)

    persons: list[Person] = []
    today = datetime.now(timezone.utc).date()
    for index in range(persons_count):
        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            position_id=None,
            first_name=f"John{index}",
            last_name=f"Doe{index}",
            middle_name=None,
            email=f"john{index}.doe@example.com",
            personnel_number=f"T-{index:03d}",
            hired_at=today,
            qualifications=[
                {
                    "name": "Safety briefing",
                    "kind": "training",
                    "issued_at": today.isoformat(),
                }
            ],
            current_ppe=[{"name": "Helmet", "status": "issued"}],
        )
        session.add(person)
        persons.append(person)
    await session.flush()

    now = datetime.now(timezone.utc)

    if training_valid or persons_count:
        delta = timedelta(days=30 if training_valid else -1)
        for person in persons:
            session.add(
                Training(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    course_name="Safety",
                    status=TrainingStatus.COMPLETED,
                    completed_at=now + delta,
                    expires_at=now + delta,
                )
            )

    if medical_valid or persons_count:
        valid_until = (now + timedelta(days=30)).date()
        expired_until = (now - timedelta(days=1)).date()
        for person in persons:
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    exam_type="periodic",
                    exam_date=now.date(),
                    valid_until=valid_until if medical_valid else expired_until,
                )
            )

    if ppe_valid or persons_count:
        expiry = now + timedelta(days=30)
        expired = now - timedelta(days=1)
        for person in persons:
            session.add(
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Helmet",
                    expires_at=expiry if ppe_valid else expired,
                )
            )

    templates: list[Template] = []
    pack = DocumentPack(
        tenant_id=tenant.slug,
        code=pack_code,
        name="Site Entry",
        description="",
    )
    session.add(pack)
    await session.flush()

    for index in range(items_count):
        template = Template(
            tenant_id=tenant.slug,
            name=f"Entry Template {index}",
            description="",
            metadata_json={},
            storage_key=f"templates/test-{index}.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.slug,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key=f"templates/test-{index}.docx",
        )
        session.add(version)

        item = DocumentPackItem(
            tenant_id=tenant.slug,
            pack_id=pack.id,
            template_id=template.id,
            order=index + 1,
            required=True,
        )
        session.add(item)
        templates.append(template)

    await session.commit()

    return SimpleNamespace(
        tenant=tenant,
        company=company,
        site=site,
        persons=persons,
        pack=pack,
        templates=templates,
    )


@pytest.mark.anyio
async def test_pack_run_enqueue(
    async_client: AsyncClient,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(session)

    captured: list[tuple[str, str]] = []

    class StubResult:
        id = "celery-task"

    def fake_apply_async(
        *,
        args: list[str],
        kwargs: dict[str, str],
        task_id: str,
        headers: dict[str, str],
    ):
        run_id = args[0]
        captured.append((run_id, kwargs.get("tenant_slug")))
        assert task_id == run_id
        assert headers.get("trace_id")
        return StubResult()

    monkeypatch.setattr("app.api.routes.packs.generate_document_task.apply_async", fake_apply_async)

    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(),
        "Idempotency-Key": f"pack-enqueue-{uuid4()}",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": data.pack.code,
            "company_id": data.company.id,
            "site_id": data.site.id,
            "person_ids": [data.persons[0].id],
            "data": {"shift": "day"},
        },
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["batch_id"]
    assert len(body["tasks"]) == 1
    task = body["tasks"][0]
    assert task["person_id"] == data.persons[0].id
    assert task["template_id"] == data.templates[0].id
    assert task["task_id"] == "celery-task"
    assert task["status"] == PipelineRunStatus.QUEUED.value
    assert captured and captured[0][1] == data.tenant.slug

    run_id = task["run_id"]
    async with sessionmaker() as verify:
        stored = await verify.get(PipelineRun, run_id)
        assert stored is not None
        assert stored.context["person"]["id"] == data.persons[0].id
        assert stored.context["company"]["id"] == data.company.id
        assert stored.context["company"]["inn"] == data.company.inn
        assert stored.context["person"]["personnel_number"] == data.persons[0].personnel_number


@pytest.mark.anyio
async def test_pack_run_multiple_persons_and_items(
    async_client: AsyncClient,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(
            session,
            persons_count=2,
            items_count=2,
        )

    captured: list[tuple[str, str]] = []

    class StubResult:
        id = "celery-task"

    def fake_apply_async(
        *,
        args: list[str],
        kwargs: dict[str, str],
        task_id: str,
        headers: dict[str, str],
    ):
        run_id = args[0]
        captured.append((run_id, kwargs.get("tenant_slug")))
        assert task_id == run_id
        assert headers.get("trace_id")
        return StubResult()

    monkeypatch.setattr("app.api.routes.packs.generate_document_task.apply_async", fake_apply_async)

    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(),
        "Idempotency-Key": f"pack-multi-{uuid4()}",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": data.pack.code,
            "company_id": data.company.id,
            "site_id": data.site.id,
            "person_ids": [person.id for person in data.persons],
            "data": {"shift": "night"},
        },
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["batch_id"]
    assert len(body["tasks"]) == 4
    person_ids = [person.id for person in data.persons]
    template_ids = [template.id for template in data.templates]
    expected_pairs = [
        (person_ids[0], template_ids[0]),
        (person_ids[0], template_ids[1]),
        (person_ids[1], template_ids[0]),
        (person_ids[1], template_ids[1]),
    ]
    actual_pairs = [(task["person_id"], task["template_id"]) for task in body["tasks"]]
    assert actual_pairs == expected_pairs
    assert len(captured) == 4
    assert all(slug == data.tenant.slug for _, slug in captured)


@pytest.mark.anyio
async def test_pack_run_requirements_validation(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(
            session,
            training_valid=False,
            medical_valid=False,
            ppe_valid=False,
        )

    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(),
        "Idempotency-Key": f"pack-validate-{uuid4()}",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": data.pack.code,
            "company_id": data.company.id,
            "site_id": data.site.id,
            "person_ids": [data.persons[0].id],
            "data": {},
        },
        headers=headers,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "http_409"
    assert body["details"]["code"] == "requirements_not_met"
    assert body["details"]["details"] == [
        {
            "person_id": data.persons[0].id,
            "violations": ["training", "medical_exam", "ppe_issue"],
        }
    ]


@pytest.mark.anyio
async def test_pack_run_start_plan_limits_active_tasks(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(session)
        tenant = data.tenant
        tenant.settings = {"plan": "start"}

        version_stmt = select(TemplateVersion).where(
            TemplateVersion.template_id == data.templates[0].id
        )
        version = (await session.execute(version_stmt)).scalar_one()

        session.add(
            PipelineRun(
                tenant_id=tenant.id,
                template_id=data.templates[0].id,
                template_version_id=version.id,
                status=PipelineRunStatus.QUEUED,
                context={},
                idempotency_key="active-run",
            )
        )
        await session.commit()

    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(),
        "Idempotency-Key": "start-plan-1",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": data.pack.code,
            "company_id": data.company.id,
            "site_id": data.site.id,
            "person_ids": [person.id for person in data.persons],
            "data": {"shift": "day"},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.headers.get("Retry-After") == "30"
    payload = response.json()
    assert payload["code"] == "http_429"
    assert payload["message"] == "A generation task is already running for this tenant"


@pytest.mark.anyio
async def test_pack_run_non_start_plan_allows_parallel_tasks(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        data = await _prepare_pack_environment(session)
        tenant = data.tenant
        tenant.settings = {"plan": "growth"}

        version_stmt = select(TemplateVersion).where(
            TemplateVersion.template_id == data.templates[0].id
        )
        version = (await session.execute(version_stmt)).scalar_one()

        session.add(
            PipelineRun(
                tenant_id=tenant.id,
                template_id=data.templates[0].id,
                template_version_id=version.id,
                status=PipelineRunStatus.RUNNING,
                context={},
                idempotency_key="active-run",
            )
        )
        await session.commit()

    captured: list[tuple[str, str]] = []

    class StubResult:
        id = "celery-task"

    def fake_apply_async(
        *,
        args: list[str],
        kwargs: dict[str, str],
        task_id: str,
        headers: dict[str, str],
    ):
        run_id = args[0]
        captured.append((run_id, kwargs.get("tenant_slug")))
        assert task_id == run_id
        assert headers.get("trace_id")
        return StubResult()

    monkeypatch.setattr("app.api.routes.packs.generate_document_task.apply_async", fake_apply_async)

    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(),
        "Idempotency-Key": "growth-plan-1",
    }

    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": data.pack.code,
            "company_id": data.company.id,
            "site_id": data.site.id,
            "person_ids": [person.id for person in data.persons],
            "data": {"shift": "evening"},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    payload = response.json()
    assert payload["batch_id"]
    assert payload["tasks"]
    assert all(task["status"] == PipelineRunStatus.QUEUED.value for task in payload["tasks"])
    assert captured and all(slug == data.tenant.slug for _, slug in captured)
