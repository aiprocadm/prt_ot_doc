from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.document import Document, DocumentStatus
from app.models.models import Template, TemplateVersion, TemplateVersionStatus, Tenant


@pytest.mark.anyio
async def test_template_version_delete_rejected_when_used(
    async_client: AsyncClient,
    sessionmaker,
    make_auth_headers,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        template = Template(
            tenant_id=tenant.slug,
            name="Safety Form",
            description="",
            metadata_json={},
            storage_key="templates/safety.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.slug,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/safety.docx",
        )
        session.add(version)
        await session.flush()

        company = await data_factory.create_company(tenant=tenant, session=session)
        user = await data_factory.create_user(tenant=tenant, session=session)

        document = Document(
            tenant_id=tenant.id,
            company_id=company.id,
            template_id=template.id,
            template_version_id=version.id,
            status=DocumentStatus.DRAFT,
            created_by=user.id,
        )
        session.add(document)
        await session.commit()

        template_id = template.id
        version_id = version.id

    headers = await make_auth_headers()
    response = await async_client.delete(
        f"/api/v1/templates/{template_id}/versions/{version_id}",
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.anyio
async def test_template_by_code_version_conflict_when_not_found(
    async_client: AsyncClient,
    make_auth_headers,
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/templates/by-code/missing",
        params={"version": 1},
        headers=headers,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "template_version_not_found"
    assert body["message"] == "Template selection by (code, version) failed"


@pytest.mark.anyio
async def test_template_version_uniqueness_constraint(
    sessionmaker,
    data_factory,
) -> None:
    """
    Test TZ-2.5-MVP-01: uniqueness of (template_id, version).

    This test verifies that the database constraint prevents creating
    two versions with the same version number for the same template.
    This is critical for strict template selection by (code, version).
    """
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        # Create a template
        template = Template(
            tenant_id=tenant.slug,
            code="unique-test-code",
            name="Template with uniqueness check",
            description="",
            metadata_json={},
            storage_key="templates/unique.docx",
        )
        session.add(template)
        await session.flush()

        # Create version 1
        version_1 = TemplateVersion(
            tenant_id=tenant.slug,
            template_id=template.id,
            version=1,
            checksum=b"checksum1",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/unique_v1.docx",
        )
        session.add(version_1)
        await session.flush()

        # Try to create another version 1 for the same template
        # This should fail due to UniqueConstraint(template_id, version)
        version_1_dup = TemplateVersion(
            tenant_id=tenant.slug,
            template_id=template.id,
            version=1,  # Same version number
            checksum=b"checksum2",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/unique_v1_dup.docx",
        )
        session.add(version_1_dup)

        # Should raise an integrity error due to uniqueness constraint
        with pytest.raises(Exception):  # IntegrityError
            await session.commit()
