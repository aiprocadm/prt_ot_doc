from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO

import pytest
from docx import Document as DocxDocument
from httpx import AsyncClient
from moto import mock_aws
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.files import s3
from app.models.document import (
    Document as DocumentModel,
    DocumentBatchItem,
    DocumentBatchRun,
    DocumentBatchStatus,
    DocumentSnapshot,
    DocumentVersion,
)
from app.models.models import Company, Outbox, TemplateVersion
from app.models.models import PipelineRun, PipelineRunStatus, RoleEnum
from app.tasks import celery_app
import app.tasks as task_module
from tests.utils.factories import TestDataFactory

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.fixture(autouse=True)
def _configure_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.setenv("S3_ACCESS_KEY", "test-access")
    monkeypatch.setenv("S3_SECRET_KEY", "test-secret")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_BACKEND", "minio")
    monkeypatch.setenv("S3_SECURE", "false")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    s3.reset_client_cache()
    yield
    s3.reset_client_cache()


@pytest.fixture()
def aws() -> None:
    with mock_aws():
        s3.ensure_bucket()
        yield


@pytest.fixture(autouse=True)
def eager_celery() -> None:
    previous_always = celery_app.conf.task_always_eager
    previous_propagates = celery_app.conf.task_eager_propagates
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = previous_always
    celery_app.conf.task_eager_propagates = previous_propagates


@pytest.fixture(autouse=True)
def override_task_session_scope(monkeypatch: pytest.MonkeyPatch, sessionmaker) -> None:
    @asynccontextmanager
    async def _scope(*, tenant: str | None = None):
        async with sessionmaker() as session:
            session.info["tenant"] = tenant or "test"
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(task_module, "session_scope", _scope)
    monkeypatch.setattr(task_module, "ensure_tenant_schema", lambda slug: None)

def _build_template_bytes() -> bytes:
    doc = DocxDocument()
    doc.add_paragraph("Hello {{ name }}!")
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


@pytest.mark.asyncio()
@pytest.mark.usefixtures("aws")
async def test_document_generation_flow(
    async_client: AsyncClient,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    template_bytes = _build_template_bytes()

    # Seed tenant-scoped entities.
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant,
            email="admin@example.com",
            role=RoleEnum.ADMIN,
            password="secret123",
            session=session,
        )
        company = await data_factory.create_company(
            tenant=tenant,
            name="ACME Corp",
            session=session,
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="John",
            last_name="Doe",
            session=session,
        )
        await session.commit()
        company_id = company.id
        person_id = person.id

    # Authenticate as seeded admin user.
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Upload template via API to reuse validation logic.
    response = await async_client.post(
        "/api/v1/templates",
        files={"file": ("greeting.docx", template_bytes, DOCX_CONTENT_TYPE)},
        data={
            "name": "Greeting",
            "metadata": "{}",
            "document_type": "greeting",
            "required_fields_schema": '{"type":"object","properties":{"name":{"type":"string"}}}',
            "applicability_rules": "{}",
            "output_types": '["docx","pdf"]',
            "profile": "{}",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    template_payload = response.json()
    template_version_id = template_payload["version_id"]

    async with sessionmaker() as session:
        template_version = await session.get(TemplateVersion, template_version_id)
        assert template_version is not None
        template_version_number = template_version.version

    headers = {"Idempotency-Key": "demo-key", **auth_headers}
    payload = {
        "template_code": "Greeting",
        "template_version": template_version_number,
        "company_id": company_id,
        "person_id": person_id,
        "data": {"name": "World"},
    }

    first = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 202, first.text
    body = first.json()
    assert body["task_id"]
    assert body["status_url"].startswith("/api/v1/documents/tasks/")

    # Document should be persisted together with version metadata.
    async with sessionmaker() as session:
        documents = (await session.execute(select(DocumentModel))).scalars().all()
        versions = (await session.execute(select(DocumentVersion))).scalars().all()
        runs = (await session.execute(select(PipelineRun))).scalars().all()
        outbox_events = (
            await session.execute(
                select(Outbox).where(Outbox.event_type == "DocumentGenerated")
            )
        ).scalars().all()

    assert len(documents) == 1
    assert len(versions) == 1
    assert len(runs) == 1
    assert len(outbox_events) == 1

    document = documents[0]
    version = versions[0]
    run = runs[0]
    outbox_event = outbox_events[0]

    assert document.company_id == company_id
    assert document.person_id == person_id
    assert document.template_id
    assert document.storage_key
    assert version.document_id == document.id
    assert version.file_key == document.storage_key
    assert version.data_json == payload["data"]
    assert run.status is PipelineRunStatus.DONE
    assert run.docx_storage_key == document.storage_key
    assert run.result_metadata.get("document_id") == document.id
    assert run.id == body["task_id"]
    assert run.result_metadata.get("company_id") == company_id
    assert run.result_metadata.get("person_id") == person_id
    assert run.result_metadata.get("payload_hash")
    assert run.context == payload["data"]
    assert outbox_event.payload["document_version_id"] == version.id

    async with sessionmaker() as session:
        snapshot = await session.get(DocumentSnapshot, version.snapshot_id)
        assert snapshot is not None
        assert snapshot.company_snapshot["name"] == "ACME Corp"

        company = await session.get(Company, company_id)
        assert company is not None
        company.name = "ACME Updated"
        await session.commit()

        refreshed = await session.get(DocumentSnapshot, version.snapshot_id)
        assert refreshed is not None
        assert refreshed.company_snapshot["name"] == "ACME Corp"

    metadata = s3.head_object(key=document.storage_key)
    assert metadata is not None
    assert metadata["size"] > 0
    assert metadata["content_type"] == DOCX_CONTENT_TYPE

    # Repeating the request with the same idempotency key must reuse the task.
    second = await async_client.post(
        "/api/v1/documents/generate",
        json=payload,
        headers=headers,
    )
    assert second.status_code == 202
    assert second.json()["task_id"] == body["task_id"]
    assert second.json()["document_version_id"] == str(version.id)

    async with sessionmaker() as session:
        doc_count = len((await session.execute(select(DocumentModel))).scalars().all())
        run_count = len((await session.execute(select(PipelineRun))).scalars().all())
        assert doc_count == 1
        assert run_count == 1

    # Changing the payload with the same key should fail.
    conflict = await async_client.post(
        "/api/v1/documents/generate",
        json={**payload, "data": {"name": "Universe"}},
        headers=headers,
    )
    assert conflict.status_code == 409
    status_check = await async_client.get(body["status_url"], headers=headers)
    assert status_check.status_code == 200
    status_payload = status_check.json()
    assert status_payload["task_id"] == body["task_id"]
    assert status_payload["status"] == PipelineRunStatus.DONE.value
    assert status_payload["document_id"] == document.id
    assert status_payload["error"] is None

    # A new idempotency key with template_code should trigger a separate pipeline run.
    id_headers = {"Idempotency-Key": "demo-key-by-id", **auth_headers}
    payload_by_id = {
        "template_code": "Greeting",
        "template_version": template_version_number,
        "company_id": company_id,
        "data": {"name": "Galaxy"},
    }

    third = await async_client.post(
        "/api/v1/documents/generate",
        json=payload_by_id,
        headers=id_headers,
    )
    assert third.status_code == 202, third.text
    third_body = third.json()


@pytest.mark.asyncio()
@pytest.mark.usefixtures("aws")
async def test_document_batch_generation_csv(
    async_client: AsyncClient,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    template_bytes = _build_template_bytes()

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant,
            email="batch@example.com",
            role=RoleEnum.ADMIN,
            password="secret123",
            session=session,
        )
        company = await data_factory.create_company(
            tenant=tenant,
            name="Batch Corp",
            session=session,
        )
        await session.commit()
        company_id = company.id

    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "batch@example.com", "password": "secret123"},
    )
    token = login.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    response = await async_client.post(
        "/api/v1/templates",
        files={"file": ("greeting.docx", template_bytes, DOCX_CONTENT_TYPE)},
        data={
            "name": "Batch Greeting",
            "metadata": "{}",
            "document_type": "batch",
            "required_fields_schema": '{"type":"object","properties":{"name":{"type":"string"}}}',
            "applicability_rules": "{}",
            "output_types": '["docx","pdf"]',
            "profile": "{}",
        },
        headers=auth_headers,
    )
    template_payload = response.json()
    template_version_id = template_payload["version_id"]

    async with sessionmaker() as session:
        template_version = await session.get(TemplateVersion, template_version_id)
        assert template_version is not None
        template_version_number = template_version.version

    csv_payload = "name\nAlice\nBob\n".encode("utf-8")
    batch_response = await async_client.post(
        "/api/v1/documents/batch",
        files={"file": ("batch.csv", csv_payload, "text/csv")},
        data={
            "template_code": "Batch Greeting",
            "template_version": template_version_number,
            "company_id": company_id,
            "naming_pattern": "batch-{row_index}-{name}",
        },
        headers=auth_headers,
    )

    assert batch_response.status_code == 202, batch_response.text
    batch_payload = batch_response.json()
    batch_id = batch_payload["id"]

    async with sessionmaker() as session:
        batch = await session.get(DocumentBatchRun, batch_id)
        assert batch is not None
        assert batch.status in {DocumentBatchStatus.RUNNING, DocumentBatchStatus.DONE}
        items = (await session.execute(select(DocumentBatchItem))).scalars().all()
        assert len(items) == 2
    assert third_body["task_id"] != body["task_id"]
    assert third_body["status_url"].startswith("/api/v1/documents/tasks/")

    async with sessionmaker() as session:
        documents_all = (await session.execute(select(DocumentModel))).scalars().all()
        versions_all = (await session.execute(select(DocumentVersion))).scalars().all()
        runs_all = (await session.execute(select(PipelineRun))).scalars().all()

    assert len(documents_all) == 2
    assert len(versions_all) == 2
    assert len(runs_all) == 2

    second_document = next(doc for doc in documents_all if doc.id != document.id)
    version_map = {ver.document_id: ver for ver in versions_all}
    second_version = version_map[second_document.id]
    second_run = next(run_item for run_item in runs_all if run_item.id != run.id)

    assert second_document.company_id == company_id
    assert second_document.person_id is None
    assert second_document.template_id == template_id
    assert second_document.storage_key
    assert second_version.file_key == second_document.storage_key
    assert second_version.data_json == payload_by_id["data"]
    assert second_run.status is PipelineRunStatus.DONE
    assert second_run.result_metadata.get("document_id") == second_document.id
    assert second_run.context == payload_by_id["data"]
    assert second_run.id == third_body["task_id"]

    metadata_second = s3.head_object(key=second_document.storage_key)
    assert metadata_second is not None
    assert metadata_second["size"] > 0
    assert metadata_second["content_type"] == DOCX_CONTENT_TYPE

    third_status = await async_client.get(third_body["status_url"], headers=auth_headers)
    assert third_status.status_code == 200
    third_status_payload = third_status.json()
    assert third_status_payload["task_id"] == third_body["task_id"]
    assert third_status_payload["document_id"] == second_document.id
    assert third_status_payload["status"] == PipelineRunStatus.DONE.value
