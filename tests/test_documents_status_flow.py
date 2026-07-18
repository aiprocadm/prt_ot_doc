from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import issue_access_token
from app.models.document import Document, DocumentStatus, DocumentVersionStatus
from app.models.models import AuditLog, RoleEnum
from tests.utils.factories import TestDataFactory


async def _seed_document(
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    *,
    status: DocumentStatus,
    role: RoleEnum = RoleEnum.ADMIN,
) -> dict[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant,
            email=f"{uuid4()}@example.com",
            role=role,
            session=session,
        )
        company = await data_factory.create_company(
            tenant=tenant,
            name=f"Company {uuid4()}"[:36],
            session=session,
        )
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            first_name="Jane",
            last_name="Doe",
            session=session,
        )
        template = await data_factory.create_template(
            tenant=tenant,
            name=f"Template {uuid4()}"[:36],
            session=session,
        )
        document, _ = await data_factory.create_document(
            tenant=tenant,
            company=company,
            person=person,
            template=template,
            creator=user,
            status=status,
            version_payload={"v": 1},
            version_file_key="documents/doc-1-v1.pdf",
            session=session,
            storage_key="documents/doc-1.pdf",
        )
        await session.commit()

        return {
            "document_id": document.id,
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "user_id": user.id,
            "role": user.role.value,
        }


async def _count_audit_logs(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        stmt = select(func.count()).select_from(AuditLog)
        return int((await session.execute(stmt)).scalar_one())


@pytest.mark.anyio()
async def test_document_status_transition_success(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.DRAFT,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )

    response = await async_client.patch(
        f"/api/v1/documents/{seeded['document_id']}/status",
        json={"to": DocumentStatus.GENERATED.value},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == DocumentStatus.GENERATED.value
    assert body["id"] == seeded["document_id"]

    async with sessionmaker() as session:
        stored_document = (
            await session.execute(select(Document).where(Document.id == seeded["document_id"]))
        ).scalar_one()
        assert stored_document.status is DocumentStatus.GENERATED

        audit_entries = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "document.status_change",
                        AuditLog.object_id == seeded["document_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audit_entries) == 1
        entry = audit_entries[0]
        assert entry.user_id == seeded["user_id"]
        assert entry.object_type == "document"
        assert entry.object_id == seeded["document_id"]
        assert entry.details == {
            "from": DocumentStatus.DRAFT.value,
            "to": DocumentStatus.GENERATED.value,
            "outcome": "success",
        }
        assert entry.changed_fields == {
            "status": {
                "from": DocumentStatus.DRAFT.value,
                "to": DocumentStatus.GENERATED.value,
            }
        }


@pytest.mark.anyio()
async def test_document_status_transition_invalid_is_rejected(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.DRAFT,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )
    before_count = await _count_audit_logs(sessionmaker)

    response = await async_client.patch(
        f"/api/v1/documents/{seeded['document_id']}/status",
        json={"to": DocumentStatus.SIGNED.value},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "DOCUMENT_INVALID_STATUS_TRANSITION"
    assert "Cannot transition document" in payload["message"]

    async with sessionmaker() as session:
        stored_document = (
            await session.execute(select(Document).where(Document.id == seeded["document_id"]))
        ).scalar_one()
        assert stored_document.status is DocumentStatus.DRAFT

    after_count = await _count_audit_logs(sessionmaker)
    assert after_count == before_count + 1

    async with sessionmaker() as session:
        latest_entry = (
            await session.execute(
                select(AuditLog)
                .where(
                    AuditLog.object_id == seeded["document_id"],
                    AuditLog.action == "document.status_change",
                )
                .order_by(AuditLog.when.desc())
            )
        ).scalar_one()
        assert latest_entry.action == "document.status_change"
        assert latest_entry.details["outcome"] == "rejected"
        assert latest_entry.details["from"] == DocumentStatus.DRAFT.value
        assert latest_entry.details["to"] == DocumentStatus.SIGNED.value


@pytest.mark.anyio()
async def test_document_status_transition_forbidden_for_unprivileged_role(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.DRAFT,
        role=RoleEnum.EMPLOYEE,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )
    before_count = await _count_audit_logs(sessionmaker)

    response = await async_client.patch(
        f"/api/v1/documents/{seeded['document_id']}/status",
        json={"to": DocumentStatus.GENERATED.value},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    after_count = await _count_audit_logs(sessionmaker)
    assert after_count == before_count


@pytest.mark.anyio()
async def test_document_status_sequential_flow(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.DRAFT,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )

    for target_status in (
        DocumentStatus.GENERATED,
        DocumentStatus.REVIEW,
        DocumentStatus.APPROVED,
        DocumentStatus.SIGNED,
        DocumentStatus.ARCHIVED,
    ):
        response = await async_client.patch(
            f"/api/v1/documents/{seeded['document_id']}/status",
            json={"to": target_status.value},
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Tenant": seeded["tenant_slug"],
            },
        )
        assert response.status_code == 200

    async with sessionmaker() as session:
        document = (
            await session.execute(select(Document).where(Document.id == seeded["document_id"]))
        ).scalar_one()
        assert document.status is DocumentStatus.ARCHIVED

        entries = (
            (
                await session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.object_type == "document",
                        AuditLog.object_id == seeded["document_id"],
                        AuditLog.action == "document.status_change",
                    )
                    .order_by(AuditLog.when)
                )
            )
            .scalars()
            .all()
        )

        assert [entry.details["to"] for entry in entries] == [
            DocumentStatus.GENERATED.value,
            DocumentStatus.REVIEW.value,
            DocumentStatus.APPROVED.value,
            DocumentStatus.SIGNED.value,
            DocumentStatus.ARCHIVED.value,
        ]
        assert all(entry.details["outcome"] == "success" for entry in entries)


@pytest.mark.anyio()
async def test_documents_list_returns_frontend_compatible_payload(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.GENERATED,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )

    response = await async_client.get(
        "/api/v1/documents",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 10
    assert payload["pagination"]["total"] >= 1
    assert payload["items"]

    item = next(entry for entry in payload["items"] if entry["id"] == seeded["document_id"])
    assert item["status"] == "ready"
    assert item["current_version_id"]
    assert item["company"]["id"]
    assert item["company"]["name"]
    assert item["history"]
    assert item["history"][0]["status"] == DocumentVersionStatus.DRAFT.value


@pytest.mark.anyio()
async def test_document_detail_and_status_return_current_version(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    seeded = await _seed_document(
        sessionmaker,
        data_factory,
        status=DocumentStatus.REVIEW,
    )
    access_token = issue_access_token(
        subject=seeded["user_id"],
        tenant=seeded["tenant_slug"],
        role=seeded["role"],
        additional_claims={"tenant_id": seeded["tenant_id"]},
    )

    detail_response = await async_client.get(
        f"/api/v1/documents/{seeded['document_id']}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )
    status_response = await async_client.get(
        f"/api/v1/documents/{seeded['document_id']}/status",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Tenant": seeded["tenant_slug"],
        },
    )

    assert detail_response.status_code == status.HTTP_200_OK
    assert status_response.status_code == status.HTTP_200_OK

    detail_payload = detail_response.json()
    status_payload = status_response.json()
    assert detail_payload["id"] == seeded["document_id"]
    assert detail_payload["current_version_id"]
    assert detail_payload["status"] == "draft"
    assert detail_payload["storage"]["url"].endswith(
        f"/api/v1/documents/{seeded['document_id']}/download"
    )
    assert status_payload["id"] == detail_payload["id"]
    assert status_payload["current_version_id"] == detail_payload["current_version_id"]
