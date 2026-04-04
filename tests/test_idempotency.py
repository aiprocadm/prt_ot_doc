import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    IdempotencyKey,
    IdempotencyStatus,
    MedicalExam,
    Person,
    PipelineRun,
    PipelineRunStatus,
    PPEIssue,
    PPEIssueStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
    Training,
    TrainingStatus,
)
from app.schemas.task import TaskAcceptedResponse


@pytest.mark.anyio
async def test_document_generate_idempotency(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        template = Template(
            tenant_id=tenant.id,
            name="SAFETY_DOC",
            description="",
            metadata_json={},
            storage_key="templates/safety.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/safety.docx",
        )
        session.add(version)

        company = Company(tenant_id=tenant.id, name="ACME LLC")
        session.add(company)
        await session.flush()

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="Jane",
            last_name="Doe",
        )
        session.add(person)
        await session.commit()

        company_id = company.id
        person_id = person.id

    calls: list[tuple[tuple, dict]] = []

    def fake_apply_async(*args, **kwargs):
        calls.append((args, kwargs))

        class _Result:
            id = kwargs.get("task_id", str(uuid.uuid4()))

        return _Result()

    monkeypatch.setattr("app.tasks._core.generate_document_task.apply_async", fake_apply_async)

    headers = {**await make_auth_headers(), "Idempotency-Key": "doc-key-123"}
    payload = {
        "template_code": "SAFETY_DOC",
        "template_version": 1,
        "company_id": company_id,
        "person_id": person_id,
        "data": {"employee": "Jane"},
    }

    first = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    second = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 202, second.text
    assert TaskAcceptedResponse.model_validate(
        second.json()
    ) == TaskAcceptedResponse.model_validate(first.json())
    assert len(calls) == 1

    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(IdempotencyKey).where(IdempotencyKey.endpoint == "documents.generate")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        record = rows[0]
        assert record.status is IdempotencyStatus.SUCCEEDED
        assert record.result_json["body"]["task_id"] == first.json()["task_id"]

        runs = (await session.execute(select(PipelineRun))).scalars().all()
        assert len(runs) == 1
        assert runs[0].status in {PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING}


@pytest.mark.anyio
async def test_pack_run_idempotency(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug

        company = Company(tenant_id=tenant.id, name="Widgets LLC")
        session.add(company)
        await session.flush()

        template = Template(
            tenant_id=tenant.id,
            name="ENTRY_FORM",
            description="",
            metadata_json={},
            storage_key="templates/entry.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/entry.docx",
        )
        session.add(version)

        pack = DocumentPack(
            tenant_id=tenant.id,
            code="ENTRY",
            name="Entry Pack",
            description="",
        )
        session.add(pack)
        await session.flush()

        item = DocumentPackItem(
            tenant_id=tenant.id,
            pack_id=pack.id,
            template_id=template.id,
            template_version_id=version.id,
            order=1,
            required=True,
        )
        session.add(item)

        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            first_name="John",
            last_name="Smith",
        )
        session.add(person)

        now = datetime.now(timezone.utc)
        await session.flush()
        session.add(
            Training(
                tenant_id=tenant.id,
                person_id=person.id,
                course_name="Safety",
                status=TrainingStatus.COMPLETED,
                completed_at=now + timedelta(days=30),
                expires_at=now + timedelta(days=30),
            )
        )
        session.add(
            MedicalExam(
                tenant_id=tenant.id,
                person_id=person.id,
                exam_type="periodic",
                exam_date=now.date(),
                valid_until=(now + timedelta(days=30)).date(),
            )
        )
        session.add(
            PPEIssue(
                tenant_id=tenant.id,
                person_id=person.id,
                item_name="Helmet",
                status=PPEIssueStatus.ISSUED,
                expires_at=now + timedelta(days=30),
            )
        )

        await session.commit()

        company_id = company.id
        pack_code = pack.code
        person_id = person.id

    task_calls: list[str] = []

    class StubResult:
        def __init__(self, run_id: str) -> None:
            self.id = f"queued-{run_id}"

    def fake_apply_async(
        *,
        args: list[str],
        kwargs: dict[str, str],
        task_id: str,
        headers: dict[str, str],
    ):
        run_id = args[0]
        task_calls.append(run_id)
        assert kwargs.get("tenant_slug")
        assert headers.get("trace_id")
        assert task_id == run_id
        return StubResult(run_id)

    monkeypatch.setattr("app.api.routes.packs.generate_document_task.apply_async", fake_apply_async)

    headers = {**await make_auth_headers(), "Idempotency-Key": "pack-key-123"}
    payload = {
        "pack_code": pack_code,
        "company_id": company_id,
        "person_ids": [person_id],
        "site_id": None,
        "context": {},
    }

    first = await async_client.post(
        "/api/v1/packs/run",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    second = await async_client.post(
        "/api/v1/packs/run",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 202, second.text
    assert first.json() == second.json()
    assert len(task_calls) == 1

    async with sessionmaker() as session:
        records = (
            (
                await session.execute(
                    select(IdempotencyKey).where(IdempotencyKey.endpoint == "packs.run")
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 1
        assert records[0].status is IdempotencyStatus.SUCCEEDED
        body = records[0].result_json["body"]
        assert body["batch_id"] == first.json()["batch_id"]


@pytest.mark.anyio
async def test_documents_generate_requires_idempotency_key(
    async_client: AsyncClient,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/documents/generate",
        json={
            "template_code": "demo",
            "template_version": 1,
            "company_id": "company",
            "data": {},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["code"] == "http_400"
    assert payload["message"] == "Idempotency-Key header is required"


@pytest.mark.anyio
async def test_packs_run_requires_idempotency_key(
    async_client: AsyncClient,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.post(
        "/api/v1/packs/run",
        json={
            "pack_code": "ANY",
            "company_id": "company",
            "site_id": None,
            "person_ids": [],
            "data": {},
        },
        headers=headers,
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    payload = response.json()
    assert payload["code"] == "http_400"
    assert payload["message"] == "Idempotency-Key header is required"
