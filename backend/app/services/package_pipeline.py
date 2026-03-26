from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.packs.definitions import (
    PACK_CODE_INCIDENT,
    PACK_CODE_NEW_COMPANY,
    PACK_CODE_SITE_ACCESS,
)
from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    Person,
    Site,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
)
from app.services.package_export import ExportDocument, PackageExportResult, PackageExportService
from app.services.pipeline import PipelineService


class DocumentPackageType(StrEnum):
    """Supported package scenarios."""

    ENTER_SITE = "enter_site"
    INCIDENT = "incident_response"
    PREPARE_INSPECTION = "prepare_inspection"
    NEW_COMPANY = "new_company"


PACK_TYPE_CODE_MAP: dict[DocumentPackageType, str] = {
    DocumentPackageType.ENTER_SITE: PACK_CODE_SITE_ACCESS,
    DocumentPackageType.INCIDENT: PACK_CODE_INCIDENT,
    DocumentPackageType.PREPARE_INSPECTION: PACK_CODE_NEW_COMPANY,
    DocumentPackageType.NEW_COMPANY: PACK_CODE_NEW_COMPANY,
}


@dataclass(slots=True)
class PackRenderSpec:
    template: Template
    version: TemplateVersion
    context: dict[str, object]
    person_id: str | None
    person_label: str | None
    run_key: str


class PackGenerationPipeline:
    """High level orchestrator for document pack generation."""

    def __init__(
        self,
        *,
        pipeline: PipelineService | None = None,
        exporter: PackageExportService | None = None,
    ) -> None:
        self.pipeline = pipeline or PipelineService()
        self.exporter = exporter or PackageExportService()

    async def plan_documents(
        self,
        session: AsyncSession,
        *,
        pack: DocumentPack,
        company: Company,
        site: Site | None,
        persons: Sequence[Person] | None,
        payload: object,
        context_builder: Callable[..., dict[str, object]],
    ) -> list[PackRenderSpec]:
        items = (
            (
                await session.execute(
                    select(DocumentPackItem)
                    .where(DocumentPackItem.pack_id == pack.id)
                    .options(
                        selectinload(DocumentPackItem.template),
                        selectinload(DocumentPackItem.template_version),
                    )
                    .order_by(DocumentPackItem.order.asc())
                )
            )
            .scalars()
            .all()
        )
        targets: list[Person | None] = list(persons or [None])
        specs: list[PackRenderSpec] = []
        for person in targets:
            context = context_builder(
                pack=pack,
                company=company,
                site=site,
                person=person,
                payload=payload,
            )
            for item in items:
                template = item.template
                if template is None:
                    raise ValueError("Pack item is missing a template")
                if item.template_version_id is None:
                    raise ValueError("Pack item requires template_version_id")
                version = item.template_version
                if version is None:
                    version = await session.get(TemplateVersion, item.template_version_id)
                if version is None:
                    raise ValueError("Pack item references missing template version")
                if version.template_id != template.id:
                    raise ValueError("Pack item template version mismatch")
                person_id = person.id if person else None
                run_key = build_idempotency_key(
                    pack=pack,
                    template=template,
                    company_id=company.id,
                    site_id=site.id if site else None,
                    person_id=person_id,
                )
                specs.append(
                    PackRenderSpec(
                        template=template,
                        version=version,
                        context=context,
                        person_id=person_id,
                        person_label=person_label(person),
                        run_key=run_key,
                    )
                )
        return specs

    async def render_documents(
        self,
        session: AsyncSession,
        *,
        specs: Iterable[PackRenderSpec],
        tenant_slug: str,
        include_docx: bool,
        include_pdf: bool,
    ) -> list[ExportDocument]:
        export_documents: list[ExportDocument] = []
        for spec in specs:
            run = await self.pipeline.run(
                session=session,
                template=spec.template,
                template_version=spec.version,
                context=spec.context,
                replacements=None,
                header_text=None,
                footer_text=None,
                idempotency_key=spec.run_key,
                output_basename=None,
                tenant_id=tenant_slug,
            )
            outputs = dict(getattr(run, "outputs", None) or {})
            metadata = dict(getattr(run, "result_metadata", None) or {})
            document_version_id = (
                outputs.get("document_version_id")
                or metadata.get("document_version_id")
                or getattr(run, "id", None)
                or spec.run_key
            )
            if include_docx and not run.docx_storage_key:
                raise RuntimeError("DOCX output missing for generated document")
            if include_pdf and not run.pdf_storage_key:
                raise RuntimeError("PDF output missing for generated document")
            export_documents.append(
                ExportDocument(
                    template_id=spec.template.id,
                    template_name=spec.template.name,
                    version=spec.version.version,
                    person_id=spec.person_id,
                    person_label=spec.person_label,
                    document_version_id=str(document_version_id),
                    docx_storage_key=run.docx_storage_key if include_docx else None,
                    pdf_storage_key=run.pdf_storage_key if include_pdf else None,
                )
            )
        return export_documents

    def export_package(
        self,
        *,
        tenant_slug: str,
        pack: DocumentPack,
        naming: dict[str, object],
        documents: Iterable[ExportDocument],
    ) -> PackageExportResult:
        return self.exporter.export(
            tenant_slug=tenant_slug,
            pack_code=pack.code,
            org=str(naming["org"]),
            unit=str(naming["unit"]),
            project=str(naming["project"]),
            client=str(naming["client"]),
            topic=str(naming["topic"]),
            version=int(naming["version"]),
            reference_date=naming["reference_date"],
            flags=naming.get("flags", ()),
            documents=documents,
        )


async def get_active_template_version(session: AsyncSession, template: Template) -> TemplateVersion:
    stmt = (
        select(TemplateVersion)
        .where(
            TemplateVersion.template_id == template.id,
            TemplateVersion.status == TemplateVersionStatus.ACTIVE,
        )
        .order_by(TemplateVersion.version.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalar_one_or_none()
    if version is None:
        raise ValueError(f"Template {template.name} has no active version")
    return version


def build_idempotency_key(
    *,
    pack: DocumentPack,
    template: Template,
    company_id: str,
    site_id: str | None,
    person_id: str | None,
) -> str:
    raw = ":".join(
        [
            "pack",
            str(pack.id),
            template.id,
            company_id,
            site_id or "-",
            person_id or "-",
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def person_label(person: Person | None) -> str | None:
    if person is None:
        return None
    parts = [person.last_name, person.first_name, person.middle_name or ""]
    joined = " ".join(part for part in parts if part)
    return joined or None


__all__ = [
    "DocumentPackageType",
    "PackGenerationPipeline",
    "PackRenderSpec",
    "build_idempotency_key",
    "get_active_template_version",
    "person_label",
]
