from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domains.packs.definitions import (
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_SITE_ACCESS,
)
from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    DocumentPackModule,
    DocumentPackScenario,
    Person,
    TemplateVersion,
    TemplateVersionStatus,
)
from app.services.package_pipeline import PackGenerationPipeline
from tests.utils.factories import TestDataFactory


class _StubPipeline:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    async def run(self, *, template, template_version, **_kwargs):
        self.calls.append((template.id, template_version.id, _kwargs.get("tenant_id")))
        return SimpleNamespace(
            docx_storage_key=f"docx-{template.id}",
            pdf_storage_key=f"pdf-{template.id}",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pack_code,scenario_type",
    [
        (PACK_CODE_SITE_ACCESS, DocumentPackScenario.DOCUMENT_BATCH),
        (PACK_CODE_INCIDENT, DocumentPackScenario.WORKFLOW),
        (PACK_CODE_INSPECTION_PREP, DocumentPackScenario.WORKFLOW),
    ],
)
async def test_pack_pipeline_plans_and_renders(
    sessionmaker, data_factory: TestDataFactory, pack_code: str, scenario_type: DocumentPackScenario
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company: Company = await data_factory.create_company(tenant=tenant, session=session)
        person: Person = await data_factory.create_person(
            tenant=tenant, company=company, session=session
        )
        template = await data_factory.create_template(tenant=tenant, session=session)
        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"123",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="template.docx",
        )
        session.add(version)

        pack = DocumentPack(
            tenant_id=tenant.id,
            code=pack_code,
            name="Scenario pack",
            module=DocumentPackModule.OT,
            scenario_type=scenario_type,
        )
        session.add(pack)
        await session.flush()

        item = DocumentPackItem(
            tenant_id=tenant.id,
            pack_id=pack.id,
            template_id=template.id,
            template_version_id=version.id,
            order=1,
        )
        session.add(item)
        await session.commit()
        await session.refresh(pack)
        await session.refresh(version)

        pipeline = PackGenerationPipeline(pipeline=_StubPipeline())
        specs = await pipeline.plan_documents(
            session,
            pack=pack,
            company=company,
            site=None,
            persons=[person],
            payload={"ok": True},
            context_builder=lambda **kwargs: {"company": kwargs["company"].name},
        )

        assert len(specs) == 1
        assert specs[0].version.id == version.id

        documents = await pipeline.render_documents(
            session,
            specs=specs,
            tenant_slug=tenant.slug,
            include_docx=True,
            include_pdf=True,
        )

        assert len(documents) == 1
        assert documents[0].docx_storage_key.startswith("docx-")
        assert pipeline.pipeline.calls
        assert pipeline.pipeline.calls[0][2] == tenant.id


@pytest.mark.asyncio
async def test_pack_pipeline_uses_explicit_template_version(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company: Company = await data_factory.create_company(tenant=tenant, session=session)
        template = await data_factory.create_template(tenant=tenant, session=session)
        version_one = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"111",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="template-v1.docx",
        )
        version_two = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=2,
            checksum=b"222",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="template-v2.docx",
        )
        session.add_all([version_one, version_two])

        pack = DocumentPack(
            tenant_id=tenant.id,
            code=PACK_CODE_SITE_ACCESS,
            name="Versioned pack",
            module=DocumentPackModule.OT,
            scenario_type=DocumentPackScenario.DOCUMENT_BATCH,
        )
        session.add(pack)
        await session.flush()

        item = DocumentPackItem(
            tenant_id=tenant.id,
            pack_id=pack.id,
            template_id=template.id,
            template_version_id=version_one.id,
            order=1,
        )
        session.add(item)
        await session.commit()

        pipeline = PackGenerationPipeline(pipeline=_StubPipeline())
        specs = await pipeline.plan_documents(
            session,
            pack=pack,
            company=company,
            site=None,
            persons=None,
            payload={"versioned": True},
            context_builder=lambda **kwargs: {"company": kwargs["company"].name},
        )

        assert specs[0].version.id == version_one.id
