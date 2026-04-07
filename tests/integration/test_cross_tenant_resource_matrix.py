"""Матрица cross-tenant HTTP: чужой id при валидном JWT+X-Tenant → ожидаемый статус."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from app.core.security import issue_access_token
from app.db.session import AsyncSessionLocal
from app.middleware.tenant import TenantMiddleware
from app.models.document import (
    DocumentBatchItem,
    DocumentBatchItemStatus,
    DocumentBatchRun,
    DocumentBatchStatus,
)
from app.models.models import Outbox, OutboxStatus, RoleEnum, Template, TemplateVersion, TemplateVersionStatus, Tenant

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _minimal_docx_bytes() -> bytes:
    doc = DocxDocument()
    doc.add_paragraph("cross-tenant tpl")
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
from app.modules.files.models import FileRecord, FileStatus


async def _ensure_global_tenant(*, slug: str = "test", tenant_id: str | None = None) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            return
        payload: dict[str, object] = {"slug": slug, "name": slug.title(), "contact_email": f"{slug}@example.com"}
        if tenant_id is not None:
            payload["id"] = tenant_id
        session.add(Tenant(**payload))
        await session.commit()


@pytest.fixture(autouse=True)
def _bypass_tenant_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch_passthrough(self, request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)

    monkeypatch.setattr(TenantMiddleware, "dispatch", _dispatch_passthrough)


def _headers_tenant_b(*, user_id: str, tenant_b: Tenant) -> dict[str, str]:
    token = issue_access_token(
        subject=user_id,
        tenant=tenant_b.slug,
        role=RoleEnum.ADMIN.value,
        additional_claims={"tenant_id": str(tenant_b.id)},
    )
    return {"Authorization": f"Bearer {token}", "x-tenant": str(tenant_b.id)}


@pytest.mark.anyio
async def test_files_v2_record_returns_404_for_other_tenant_file(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="files-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="files-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        rec = FileRecord(
            tenant_id=ta.id,
            bucket="test",
            object_key=f"tenants/{ta.slug}/cross-mx.bin",
            content_type="application/octet-stream",
            size_bytes=1,
            sha256="a" * 64,
            status=FileStatus.clean.value,
        )
        session.add(rec)
        await session.commit()
        fid = rec.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.get(
        f"/api/v1/files/records/{fid}",
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_admin_outbox_get_returns_404_for_other_tenant_row(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="outbox-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="outbox-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        entry = Outbox(
            tenant_id=ta.id,
            event_type="DocumentCreated",
            destination="https://example.test/h",
            payload={},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
            idempotency_key="idem-mx-outbox",
        )
        session.add(entry)
        await session.commit()
        oid = entry.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.get(
        f"/api/v1/admin/outbox/{oid}",
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_documents_batch_get_returns_404_for_other_tenant_batch(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="batch-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="batch-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        user_a = await data_factory.create_user(tenant=ta, role=RoleEnum.ADMIN, session=session)
        company = await data_factory.create_company(tenant=ta, session=session)
        template = Template(
            tenant_id=ta.id,
            name="batch-mx-tpl",
            metadata_json={},
            storage_key="batch-mx/tpl.docx",
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=ta.id,
            template_id=template.id,
            version=1,
            checksum=b"chk",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="batch-mx/tpl.docx",
        )
        session.add(version)
        await session.flush()
        batch = DocumentBatchRun(
            tenant_id=ta.id,
            template_id=template.id,
            template_version_id=version.id,
            company_id=company.id,
            created_by=user_a.id,
            status=DocumentBatchStatus.PENDING,
            total=1,
            processed=0,
            succeeded=0,
            failed=0,
        )
        session.add(batch)
        await session.flush()
        session.add(
            DocumentBatchItem(
                tenant_id=ta.id,
                batch_id=batch.id,
                row_index=0,
                payload={},
                status=DocumentBatchItemStatus.PENDING,
            )
        )
        await session.commit()
        batch_id = batch.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.get(
        f"/api/v1/documents/batch/{batch_id}",
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_legacy_post_template_version_returns_404_for_other_tenant_template(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="tpl-ver-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="tpl-ver-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        template = Template(
            tenant_id=ta.id,
            name="tpl-ver-mx-name",
            code="tpl-ver-mx-code",
            metadata_json={},
        )
        session.add(template)
        await session.commit()
        template_id = template.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.post(
        f"/api/v1/templates/{template_id}/versions",
        files={"file": ("t.docx", _minimal_docx_bytes(), DOCX_CONTENT_TYPE)},
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_sites_get_returns_404_for_other_tenant_site(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="sites-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="sites-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        company_a = await data_factory.create_company(tenant=ta, session=session)
        site_a = await data_factory.create_site(tenant=ta, company=company_a, session=session)
        await session.commit()
        site_id = site_a.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.get(
        f"/api/v1/sites/{site_id}",
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_documents_get_returns_404_for_other_tenant_document(
    async_client,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        ta = await data_factory.ensure_tenant(slug="docs-mx-a", session=session)
        tb = await data_factory.ensure_tenant(slug="docs-mx-b", session=session)
        user_b = await data_factory.create_user(tenant=tb, role=RoleEnum.ADMIN, session=session)
        company_a = await data_factory.create_company(tenant=ta, session=session)
        document_a, _ = await data_factory.create_document(tenant=ta, company=company_a, session=session)
        await session.commit()
        document_id = document_a.id
        user_b_id = user_b.id

    await _ensure_global_tenant(slug=ta.slug, tenant_id=str(ta.id))
    await _ensure_global_tenant(slug=tb.slug, tenant_id=str(tb.id))

    response = await async_client.get(
        f"/api/v1/documents/{document_id}",
        headers=_headers_tenant_b(user_id=user_b_id, tenant_b=tb),
    )
    assert response.status_code == 404
