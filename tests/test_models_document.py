from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.models import Company, Person, RoleEnum, Template, Tenant, User
from app.services.documents import DocumentVersionUpdateError


@pytest.mark.asyncio()
async def test_document_and_versions_relationship(sessionmaker):
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        user = User(
            tenant_id=tenant.id,
            email="owner@example.com",
            full_name="Owner User",
            role=RoleEnum.ADMIN,
            hashed_password="hashed",
        )

        company = Company(tenant_id=tenant.id, name="ACME")
        person = Person(
            tenant_id=tenant.id,
            company=company,
            first_name="John",
            last_name="Doe",
        )
        template = Template(tenant_id=tenant.id, name="Contract")

        session.add_all([user, company, person, template])
        await session.flush()

        document = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=person.id,
            template_id=template.id,
            status=DocumentStatus.REVIEW,
            created_by=user.id,
            storage_key="contracts/1.docx",
        )
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document=document,
            template_version="v1",
            data_json={"field": "value"},
            file_key="contracts/1-v1.pdf",
        )
        session.add(version)
        await session.commit()

        refreshed_document = (
            await session.execute(
                select(Document)
                .options(selectinload(Document.versions))
                .where(Document.id == document.id)
            )
        ).scalar_one()

        assert refreshed_document.status is DocumentStatus.REVIEW
        assert refreshed_document.versions[0].file_key == "contracts/1-v1.pdf"
        assert refreshed_document.versions[0].document_id == refreshed_document.id
        assert refreshed_document.versions[0].tenant_id == refreshed_document.tenant_id
        assert refreshed_document.versions[0].data_json == {"field": "value"}

        stored_version = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == version.id))
        ).scalar_one()
        assert stored_version.document.id == refreshed_document.id


@pytest.mark.asyncio()
async def test_document_version_update_is_forbidden(sessionmaker):
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        user = User(
            tenant_id=tenant.id,
            email="editor@example.com",
            full_name="Editor User",
            role=RoleEnum.ADMIN,
            hashed_password="hashed",
        )
        company = Company(tenant_id=tenant.id, name="Immutable LLC")
        template = Template(tenant_id=tenant.id, name="Immutable Template")

        session.add_all([user, company, template])
        await session.flush()

        document = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            person_id=None,
            template_id=template.id,
            status=DocumentStatus.DRAFT,
            created_by=user.id,
            storage_key="immutable.docx",
        )
        session.add(document)
        await session.flush()

        version = DocumentVersion(
            document=document,
            template_version="v1",
            data_json={"field": "value"},
            file_key="immutable-v1.docx",
        )
        session.add(version)
        await session.commit()

        stored_version = (
            await session.execute(select(DocumentVersion).where(DocumentVersion.id == version.id))
        ).scalar_one()
        stored_version.file_key = "immutable-v1-updated.docx"

        with pytest.raises(DocumentVersionUpdateError):
            await session.flush()

        await session.rollback()
