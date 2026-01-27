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
