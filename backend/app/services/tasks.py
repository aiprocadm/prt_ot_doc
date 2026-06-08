from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine, Iterable
from datetime import date, datetime, timezone
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.metrics import get_metrics
from app.db.session import AsyncSessionLocal
from app.domains.packs.context import enrich_context
from app.domains.packs.seeder import ensure_default_packs
from app.models.models import (
    Company,
    DocumentPack,
    DocumentPackItem,
    MedicalExam,
    Person,
    PipelineRun,
    PPEIssue,
    PPEIssueStatus,
    Site,
    Training,
    TrainingStatus,
)
from app.schemas.pack import PackGenerateRequest
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.celery_app import settings as celery_settings
from app.services.events import EventType
from app.services.outbox import OutboxService
from app.services.package_pipeline import PackGenerationPipeline, person_label
from app.services.pipeline import PipelineService

logger = logging.getLogger(__name__)


def _pipeline_run_coroutine(
    run_id: str, tenant_slug: str
) -> Coroutine[None, None, str]:
    async def _run() -> str:
        async with AsyncSessionLocal(tenant=tenant_slug) as session:
            stmt = (
                select(PipelineRun)
                .options(
                    selectinload(PipelineRun.template),
                    selectinload(PipelineRun.template_version),
                )
                .where(PipelineRun.id == run_id)
            )
            result = await session.execute(stmt)
            run = result.scalar_one_or_none()
            if run is None:
                raise ValueError(f"Pipeline run {run_id} not found")

            request_meta = dict((run.result_metadata or {}).get("request") or {})
            service = PipelineService()
            updated = await service.run(
                session=session,
                template=run.template,
                template_version=run.template_version,
                context=run.context,
                replacements=request_meta.get("replacements"),
                header_text=request_meta.get("header_text"),
                footer_text=request_meta.get("footer_text"),
                idempotency_key=run.idempotency_key,
                output_basename=request_meta.get("output_basename"),
                tenant_id=run.tenant_id,
            )
            return updated.id

    return _run()


def _execute_pipeline_run(run_id: str, tenant_slug: str, *, task_name: str) -> str:
    queue = (
        celery_settings.celery.pdf_queue
        or celery_app.conf.task_default_queue
        or "default"
    )
    metrics = get_metrics()
    metrics.record_celery_enqueue(queue=queue, task=task_name)

    started = perf_counter()
    try:
        result = asyncio.run(_pipeline_run_coroutine(run_id, tenant_slug))
    except Exception as exc:  # noqa: BLE001 - propagate Celery failure
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception(
            "pipeline_task.failed",
            extra={"task": task_name, "run_id": run_id, "tenant": tenant_slug},
        )
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="pipeline.run",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def run_pipeline_task(self, run_id: str, tenant_slug: str) -> str:
    """Execute a queued pipeline run for the given tenant."""

    return _execute_pipeline_run(run_id, tenant_slug, task_name="pipeline.run")


@celery_app.task(
    name="documents.generate",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def generate_document_task(self, run_id: str, tenant_slug: str) -> str:
    """Alias task for document generation to maintain semantic clarity."""

    return _execute_pipeline_run(run_id, tenant_slug, task_name="documents.generate")


def _tenant_scope_values(tenant_slug: str, tenant_id: str | None) -> tuple[str, ...]:
    values: list[str] = [tenant_slug]
    if tenant_id:
        values.append(str(tenant_id))
    return tuple(values)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def _load_company(
    session: AsyncSessionLocal, *, tenant_scope: tuple[str, ...], company_id: str
) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.deleted_at.is_(None),
        Company.tenant_id.in_(tenant_scope),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise ValueError("Company not found")
    return company


async def _load_site(
    session: AsyncSessionLocal,
    *,
    tenant_scope: tuple[str, ...],
    company: Company,
    site_id: str | None,
) -> Site | None:
    if site_id is None:
        return None
    stmt = select(Site).where(
        Site.id == site_id,
        Site.deleted_at.is_(None),
        Site.tenant_id.in_(tenant_scope),
    )
    site = (await session.execute(stmt)).scalar_one_or_none()
    if site is None:
        raise ValueError("Site not found")
    if site.company_id != company.id:
        raise ValueError("Site does not belong to company")
    return site


async def _load_persons(
    session: AsyncSessionLocal,
    *,
    tenant_scope: tuple[str, ...],
    company: Company,
    person_ids: Iterable[str],
) -> list[Person]:
    ids = [pid for pid in person_ids if pid]
    if not ids:
        return []
    unique_ids: list[str] = []
    seen = set()
    for pid in ids:
        if pid not in seen:
            unique_ids.append(pid)
            seen.add(pid)
    stmt = select(Person).where(
        Person.id.in_(unique_ids),
        Person.deleted_at.is_(None),
        Person.tenant_id.in_(tenant_scope),
    )
    persons = list((await session.execute(stmt)).scalars().all())
    if len(persons) != len(unique_ids):
        raise ValueError("One or more persons were not found")
    indexed = {person.id: person for person in persons}
    ordered: list[Person] = []
    for pid in unique_ids:
        person = indexed[pid]
        if person.company_id != company.id:
            raise ValueError("Person does not belong to the specified company")
        ordered.append(person)
    return ordered


async def _enforce_person_invariants(
    session: AsyncSessionLocal, *, tenant_scope: tuple[str, ...], persons: list[Person]
) -> None:
    from app.services.person_admission import enforce_person_admission

    await enforce_person_admission(session, tenant_scope=tenant_scope, persons=persons)


async def _load_pack(
    session: AsyncSessionLocal,
    *,
    tenant_scope: tuple[str, ...],
    tenant_slug: str,
    pack_code: str,
) -> DocumentPack:
    await ensure_default_packs(session, tenant_slug=tenant_slug)
    stmt = select(DocumentPack).where(
        DocumentPack.code == pack_code,
        DocumentPack.tenant_id.in_(tenant_scope),
        DocumentPack.is_active.is_(True),
        DocumentPack.deleted_at.is_(None),
    ).options(
        selectinload(DocumentPack.items).selectinload(DocumentPackItem.template),
        selectinload(DocumentPack.items).selectinload(DocumentPackItem.template_version),
    )
    pack = (await session.execute(stmt)).scalar_one_or_none()
    if pack is None:
        raise ValueError("Pack not found")
    if not pack.items:
        raise ValueError("Pack contains no items")
    return pack


def _build_context(
    *,
    pack: DocumentPack,
    company: Company,
    site: Site | None,
    person: Person | None,
    payload: PackGenerateRequest,
) -> dict[str, object]:
    company_payload = {
        "id": company.id,
        "name": company.name,
        "tax_id": company.tax_id,
        "address": company.address,
        "inn": company.tax_id,
    }
    context: dict[str, object] = {
        "pack_code": pack.code,
        "company": company_payload,
        "data": dict(payload.data),
    }
    if site is not None:
        context["site"] = {
            "id": site.id,
            "name": site.name,
            "address": site.address,
        }
    if person is not None:
        context["person"] = {
            "id": person.id,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "middle_name": person.middle_name,
            "company_id": person.company_id,
            "position_id": person.position_id,
            "personnel_number": person.personnel_number,
            "hired_at": person.hired_at.isoformat() if person.hired_at else None,
            "qualifications": list(person.qualifications or []),
            "snils": person.snils,
            "passport": person.passport,
            "current_ppe": list(person.current_ppe or []),
        }
    return enrich_context(pack.code, context, dict(payload.data))


def _coerce_string(value: object | None, default: str) -> str:
    if value is None:
        return default
    result = str(value).strip()
    return result or default


def _resolve_naming(
    payload: PackGenerateRequest, company: Company, site: Site | None, pack: DocumentPack
) -> dict[str, object]:
    config = payload.naming
    org = _coerce_string(config.org, company.name)
    unit = _coerce_string(config.unit, site.name if site else "hq")
    project = _coerce_string(
        config.project, payload.data.get("project") if payload.data else pack.code
    )
    client = _coerce_string(config.client, company.name)
    topic = _coerce_string(config.topic, pack.code)
    version = config.version or 1
    reference_date = config.reference_date or date.today()
    flags: list[str] = []
    flags.extend(config.flags)
    data_flags = payload.data.get("flags") if payload.data else None
    if isinstance(data_flags, list):
        for flag in data_flags:
            if isinstance(flag, str) and flag.strip():
                flags.append(flag.strip())
    deduplicated_flags = tuple(dict.fromkeys(flags))
    return {
        "org": org,
        "unit": unit,
        "project": project,
        "client": client,
        "topic": topic,
        "version": version,
        "reference_date": reference_date,
        "flags": deduplicated_flags,
    }


async def _generate_pack_coroutine(
    *, tenant_slug: str, tenant_id: str | None, payload: dict[str, object]
) -> dict[str, object]:
    request = PackGenerateRequest.model_validate(payload)
    if not (request.include_docx or request.include_pdf):
        raise ValueError("At least one of include_docx or include_pdf must be enabled")

    async with AsyncSessionLocal(tenant=tenant_slug) as session:
        tenant_scope = _tenant_scope_values(tenant_slug, tenant_id)
        company = await _load_company(
            session, tenant_scope=tenant_scope, company_id=request.company_id
        )
        site = await _load_site(
            session,
            tenant_scope=tenant_scope,
            company=company,
            site_id=request.site_id,
        )
        persons = await _load_persons(
            session,
            tenant_scope=tenant_scope,
            company=company,
            person_ids=request.person_ids,
        )
        await _enforce_person_invariants(
            session, tenant_scope=tenant_scope, persons=persons
        )

        pack = await _load_pack(
            session,
            tenant_scope=tenant_scope,
            tenant_slug=tenant_slug,
            pack_code=request.pack_code,
        )
        pipeline_service = PackGenerationPipeline(pipeline=PipelineService(), exporter=None)
        naming = _resolve_naming(request, company, site, pack)

        specs = await pipeline_service.plan_documents(
            session,
            pack=pack,
            company=company,
            site=site,
            persons=persons,
            payload=request,
            context_builder=_build_context,
        )

        export_documents = await pipeline_service.render_documents(
            session,
            specs=specs,
            tenant_slug=tenant_slug,
            include_docx=request.include_docx,
            include_pdf=request.include_pdf,
        )

        if not export_documents:
            raise ValueError("Pack contains no renderable templates")

        export_result = pipeline_service.export_package(
            tenant_slug=tenant_slug,
            pack=pack,
            naming=naming,
            documents=export_documents,
        )

        person_index = {person.id: person for person in persons}
        documents_payload = [
            {
                "template_id": doc.template_id,
                "template_name": doc.template_name,
                "person_id": doc.person_id,
                "person_label": person_label(
                    person_index.get(doc.person_id) if doc.person_id else None
                ),
                "basename": doc.basename,
                "document_version_id": doc.document_version_id,
                "docx_storage_key": doc.docx_storage_key,
                "pdf_storage_key": doc.pdf_storage_key,
                "docx_zip_path": doc.docx_zip_path,
                "pdf_zip_path": doc.pdf_zip_path,
            }
            for doc in export_result.documents
        ]

        audit_payload = {
            "pack_code": pack.code,
            "company_id": company.id,
            "site_id": site.id if site else None,
            "person_ids": [person.id for person in persons],
            "documents": documents_payload,
            "data": request.data,
            "naming": {
                **{
                    k: (v.isoformat() if isinstance(v, date) else v)
                    for k, v in naming.items()
                },
            },
        }
        outbox = OutboxService(session)
        await outbox.enqueue(
            tenant_id=str(company.tenant_id),
            event_type=EventType.DOCUMENT_EXPORTED.value,
            payload={
                "tenant_id": str(company.tenant_id),
                "actor_id": None,
                "occurred_at": datetime.now(tz=timezone.utc),
                "pack_id": pack.id,
                "pack_code": pack.code,
                "zip_storage_key": export_result.zip_storage_key,
                "documents": documents_payload,
            },
        )
        audit = AuditService(session)
        await audit.log_event(
            tenant_id=str(company.tenant_id),
            action="pack.generate",
            object_type="document_pack",
            object_id=pack.id,
            user_id=None,
            ip="system",
            details=audit_payload,
            changed_fields=audit_payload,
        )
        await session.commit()

    return {
        "status": "success",
        "tenant": tenant_slug,
        "pack_id": pack.id,
        "pack_code": pack.code,
        "zip_storage_key": export_result.zip_storage_key,
        "documents": documents_payload,
    }


def _execute_pack_generation(
    *, tenant_slug: str, tenant_id: str | None, payload: dict[str, object], task_name: str
) -> dict[str, object]:
    queue = (
        celery_settings.celery.pdf_queue
        or celery_app.conf.task_default_queue
        or "default"
    )
    metrics = get_metrics()
    metrics.record_celery_enqueue(queue=queue, task=task_name)

    started = perf_counter()
    try:
        result = asyncio.run(
            _generate_pack_coroutine(
                tenant_slug=tenant_slug, tenant_id=tenant_id, payload=payload
            )
        )
    except Exception as exc:  # noqa: BLE001 - propagate Celery failure
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception(
            "pack_task.failed",
            extra={"task": task_name, "tenant": tenant_slug, "payload": payload},
        )
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="packs.generate",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def generate_pack_task(
    self, *, tenant_slug: str, tenant_id: str | None, payload: dict[str, object]
) -> dict[str, object]:
    """Generate a document package asynchronously for the given tenant."""

    return _execute_pack_generation(
        tenant_slug=tenant_slug,
        tenant_id=tenant_id,
        payload=payload,
        task_name="packs.generate",
    )
