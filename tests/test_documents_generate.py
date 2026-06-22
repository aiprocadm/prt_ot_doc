from __future__ import annotations

from contextlib import asynccontextmanager
from io import BytesIO

import pytest
from docx import Document as DocxDocument
from httpx import AsyncClient
from sqlalchemy import select

import app.tasks._core as task_core
from app.core.config import get_settings
from app.core.security import issue_access_token
from app.db.session import AsyncSessionLocal
from app.domains.files import s3
from app.models.document import (
    Document as DocumentModel,
)
from app.models.document import (
    DocumentBatchItem,
    DocumentBatchRun,
    DocumentBatchStatus,
    DocumentSnapshot,
    DocumentVersion,
)
from app.models.models import (
    Company,
    Outbox,
    PipelineRun,
    PipelineRunStatus,
    RoleEnum,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.tasks import celery_app
from tests.utils.factories import TestDataFactory

# moto is an optional test dependency; skip the whole module when it is absent.
# Placed after imports (which only need always-present core deps) to keep the
# import block at the top of the file.
mock_aws = pytest.importorskip("moto").mock_aws

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

    monkeypatch.setattr(task_core, "session_scope", _scope)
    monkeypatch.setattr(task_core, "ensure_tenant_schema", lambda slug: None)


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

    tenant_id = str(tenant.id)
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as public_session:
        public_tenant = (
            await public_session.execute(select(Tenant.id).where(Tenant.slug == tenant.slug))
        ).scalar_one_or_none()
        if public_tenant is not None:
            tenant_id = str(public_tenant)

    # Authenticate as seeded admin user.
    login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
        headers={"x-tenant": str(tenant.id)},
    )
    assert login.status_code == 200
    token = issue_access_token(
        subject=user.id,
        tenant=tenant.slug,
        role=user.role.value,
        additional_claims={"tenant_id": tenant_id},
    )
    auth_headers = {"Authorization": f"Bearer {token}", "x-tenant": tenant_id}

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
            (await session.execute(select(Outbox).where(Outbox.event_type == "DocumentGenerated")))
            .scalars()
            .all()
        )

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
    assert version.data_json.get("name") == payload["data"]["name"]
    assert "passport" in version.data_json
    assert version.data_json.get("correlation_id")
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
    detail = conflict.json().get("detail", {})
    assert detail.get("code") in {"IDEMPOTENCY_MISMATCH", None}
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

    tenant_id = str(tenant.id)
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as public_session:
        public_tenant = (
            await public_session.execute(select(Tenant.id).where(Tenant.slug == tenant.slug))
        ).scalar_one_or_none()
        if public_tenant is not None:
            tenant_id = str(public_tenant)

    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "batch@example.com", "password": "secret123"},
        headers={"x-tenant": str(tenant.id)},
    )
    token = issue_access_token(
        subject=user.id,
        tenant=tenant.slug,
        role=user.role.value,
        additional_claims={"tenant_id": tenant_id},
    )
    auth_headers = {"Authorization": f"Bearer {token}", "x-tenant": tenant_id}

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

    async with sessionmaker() as session:
        runs = (await session.execute(select(PipelineRun))).scalars().all()

    assert len(runs) == 2
    run_map = {run.id: run for run in runs}
    for item in items:
        assert item.pipeline_run_id is not None
        run = run_map[item.pipeline_run_id]
        assert run.context == item.payload
        assert run.result_metadata.get("batch_id") == batch_id
        assert run.result_metadata.get("row_index") == item.row_index
        assert run.result_metadata.get("output_name") == item.output_name


@pytest.mark.asyncio()
async def test_documents_list_etag_returns_304_on_if_none_match(
    async_client: AsyncClient,
    sessionmaker,
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await data_factory.create_document(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/documents", headers=headers)
    assert first.status_code == 200
    etag = first.headers.get("ETag")
    assert etag

    second = await async_client.get(
        "/api/v1/documents",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == 304
    assert second.headers.get("ETag") == etag


@pytest.mark.asyncio()
async def test_template_resolve_prefers_site_scope(
    async_client: AsyncClient,
    sessionmaker,
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)

        tenant_template = Template(
            tenant_id=tenant.id,
            name="Tenant Order",
            code="order-template",
            metadata_json={
                "scope": {"level": "tenant"},
                "case_types": ["employment"],
                "template_type": "order",
            },
        )
        company_template = Template(
            tenant_id=tenant.id,
            name="Company Order",
            code="order-template-company",
            metadata_json={
                "scope": {"level": "company", "company_id": company.id},
                "case_types": ["employment"],
                "template_type": "order",
            },
        )
        site_template = Template(
            tenant_id=tenant.id,
            name="Site Order",
            code="order-template-site",
            metadata_json={
                "scope": {"level": "site", "company_id": company.id, "site_id": site.id},
                "case_types": ["employment"],
                "template_type": "order",
            },
        )
        session.add_all([tenant_template, company_template, site_template])
        await session.flush()

        versions = [
            TemplateVersion(
                tenant_id=tenant.id,
                template_id=tenant_template.id,
                version=1,
                checksum=b"tenant-v1",
                sha256="tenant-v1",
                status=TemplateVersionStatus.ACTIVE,
                payload_key="templates/tenant-v1.docx",
            ),
            TemplateVersion(
                tenant_id=tenant.id,
                template_id=company_template.id,
                version=2,
                checksum=b"company-v2",
                sha256="company-v2",
                status=TemplateVersionStatus.ACTIVE,
                payload_key="templates/company-v2.docx",
            ),
            TemplateVersion(
                tenant_id=tenant.id,
                template_id=site_template.id,
                version=3,
                checksum=b"site-v3",
                sha256="site-v3",
                status=TemplateVersionStatus.ACTIVE,
                payload_key="templates/site-v3.docx",
            ),
        ]
        session.add_all(versions)
        await session.flush()
        tenant_template.current_version_id = versions[0].id
        company_template.current_version_id = versions[1].id
        site_template.current_version_id = versions[2].id
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        "/api/v1/documents/template:resolve",
        json={
            "case_type": "employment",
            "document_type": "order",
            "company_id": company.id,
            "site_id": site.id,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["template_code"] == "order-template-site"
    assert body["scope_level"] == "site"
    assert body["template_version"] == 3
    assert "site:exact" in body["resolution_chain"]
    assert len(body["alternatives"]) >= 1
