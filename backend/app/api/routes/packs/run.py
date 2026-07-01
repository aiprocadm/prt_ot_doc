"""Pack endpoints — run_pack, archive downloads, safety summary (ARCH-4 slice 8 split)."""

from __future__ import annotations

import uuid
import zipfile
from io import BytesIO
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session
from app.api.routes.packs._common import (
    PackReadAccess,
    PackWriteAccess,
    SessionDep,
    TenantDep,
    _build_context,
    _enforce_person_invariants,
    _get_company,
    _get_pack,
    _get_persons,
    _get_site,
    _has_single_task_limit,
    _pack_conflict,
    _tenant_scope_values,
    logger,
    router,
)
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.idempotency import compute_request_hash
from app.core.tenant import tenant_prefix_path
from app.core.tenant_validation import TenantContextValidator
from app.core.tracing import get_trace_id
from app.domains.files import s3
from app.models.file import File as StoredFile
from app.models.file import FileScanStatus
from app.models.models import (
    Person,
    PipelineRun,
    PipelineRunStatus,
    TemplateVersion,
)
from app.models.safety_core import RiskMapItem, SafetyRiskMap
from app.modules.ppe.services import PackSafetySummaryService
from app.schemas.pack import (
    PackRunRequest,
    PackRunResponse,
    PackRunTask,
)
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.package_pipeline import build_idempotency_key
from app.services.pipeline import PipelineService
from app.services.tasks import generate_document_task


@router.post("/run", response_model=PackRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def run_pack(
    payload: PackRunRequest,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: PackWriteAccess,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PackRunResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    normalized_key = normalize_idempotency_key(idempotency_key)
    idem_state = getattr(request.state, "idempotency", {})
    request_hash = idem_state.get("fingerprint")
    if request_hash is None:
        request_hash = compute_request_hash(payload)
        idem_state = {"key": normalized_key, "fingerprint": request_hash}
        request.state.idempotency = idem_state
    idempotency = IdempotencyService(
        session=session,
        tenant_id=str(tenant.id),
        endpoint="packs.run",
    )
    existing_record = await idempotency.get(key=normalized_key)

    if existing_record is None and _has_single_task_limit(tenant):
        active_stmt = (
            select(func.count())
            .select_from(PipelineRun)
            .where(
                PipelineRun.tenant_id == tenant.id,
                PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
            )
        )
        active_runs = (await session.execute(active_stmt)).scalar_one()
        if active_runs:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=api_problem_detail(
                    code="TOO_MANY_REQUESTS",
                    message="A generation task is already running for this tenant",
                    error_type="packs",
                ),
                headers={"Retry-After": "30"},
            )

    record, created_record = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method.upper(),
        path=request.url.path,
    )
    if not created_record:
        return await idempotency.respond_from_store(
            record, model=PackRunResponse, response=response
        )

    try:
        company = await _get_company(session, tenant, payload.company_id, access=access)
        site = await _get_site(session, tenant, company, payload.site_id)
        persons = await _get_persons(session, tenant, company, payload.person_ids)
        await _enforce_person_invariants(session, tenant, persons)

        pack = await _get_pack(session, tenant, payload.pack_code)
        service = PipelineService()

        batch_id = str(uuid.uuid4())
        tasks: list[PackRunTask] = []
        targets: list[Person | None] = persons or [None]

        for person in targets:
            context = _build_context(
                pack=pack,
                company=company,
                site=site,
                person=person,
                payload=payload,
            )
            context["letterhead"] = (
                payload.letterhead.model_dump(mode="json") if payload.letterhead else None
            )
            context["site_id"] = site.id if site else None
            for item in pack.items:
                template = item.template
                if template is None:
                    raise _pack_conflict(
                        "Pack item is missing a template", code="PACK_ITEM_NO_TEMPLATE"
                    )
                if item.template_version_id is None:
                    raise _pack_conflict(
                        "Pack item requires template_version_id",
                        code="PACK_ITEM_TEMPLATE_VERSION_REQUIRED",
                    )
                version = item.template_version
                if version is None:
                    version = await session.get(TemplateVersion, item.template_version_id)
                if version is None:
                    raise _pack_conflict(
                        "Pack item references missing template version",
                        code="PACK_ITEM_TEMPLATE_VERSION_MISSING",
                    )
                if str(version.tenant_id) != str(pack.tenant_id):
                    raise _pack_conflict(
                        "Pack item template version tenant mismatch",
                        code="PACK_ITEM_TEMPLATE_VERSION_TENANT_MISMATCH",
                    )
                if version.template_id != template.id:
                    raise _pack_conflict(
                        "Pack item template version mismatch",
                        code="PACK_ITEM_TEMPLATE_VERSION_MISMATCH",
                    )
                person_id = person.id if person is not None else None
                run_key = build_idempotency_key(
                    pack=pack,
                    template=template,
                    company_id=company.id,
                    site_id=site.id if site else None,
                    person_id=person_id,
                )
                run, _created = await service.ensure_pending_run(
                    session,
                    template=template,
                    template_version=version,
                    context=context,
                    replacements=None,
                    header_text=None,
                    footer_text=None,
                    idempotency_key=run_key,
                    output_basename=None,
                    tenant_id=template.tenant_id,
                )
                await session.flush()
                status_value = (
                    run.status.value
                    if isinstance(run.status, PipelineRunStatus)
                    else str(run.status)
                )
                task_identifier: str | None = None
                if run.status == PipelineRunStatus.QUEUED:
                    try:
                        trace_id = get_trace_id()
                        result = generate_document_task.apply_async(
                            args=[run.id],
                            kwargs={"tenant_slug": tenant.slug},
                            task_id=run.id,
                            headers={"trace_id": trace_id},
                        )
                        task_identifier = getattr(result, "id", None)
                    except Exception as exc:  # pragma: no cover - exercised in integration tests
                        logger.warning(
                            "generate_document_task.enqueue_failed",
                            extra={"run_id": run.id, "template_id": template.id},
                            exc_info=exc,
                        )
                        run = await service.run(
                            session=session,
                            template=template,
                            template_version=version,
                            context=context,
                            replacements=None,
                            header_text=None,
                            footer_text=None,
                            idempotency_key=run_key,
                            output_basename=None,
                            tenant_id=template.tenant_id,
                        )
                        status_value = (
                            run.status.value
                            if isinstance(run.status, PipelineRunStatus)
                            else str(run.status)
                        )
                tasks.append(
                    PackRunTask(
                        run_id=run.id,
                        template_id=template.id,
                        template_name=template.name,
                        person_id=person_id,
                        task_id=task_identifier,
                        status=status_value,
                    )
                )

        result = PackRunResponse(batch_id=batch_id, tasks=tasks)
        await idempotency.store_success(
            record,
            status_code=status.HTTP_202_ACCEPTED,
            body=result.model_dump(mode="json"),
        )
        await session.commit()
    except HTTPException as exc:
        await idempotency.store_failure(
            record,
            status_code=exc.status_code,
            detail={"detail": exc.detail},
        )
        await session.commit()
        raise
    except Exception as exc:
        await idempotency.store_failure(
            record,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": str(exc)},
        )
        await session.commit()
        raise

    response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.get("/download", summary="Download generated package archive")
async def download_pack_archive(
    tenant: TenantDep,
    access: PackReadAccess,
    request: Request,
    session: AsyncSession = Depends(get_session),
    storage_key: str = Query(
        ...,
        min_length=1,
        description="Object storage key of the generated ZIP archive",
    ),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    normalized_key = storage_key.strip()
    if not normalized_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="INVALID_STORAGE_KEY",
                message="storage_key must not be empty",
                error_type="packs",
            ),
        )
    tenant_prefix = f"{tenant_prefix_path(tenant.slug)}/"
    if not normalized_key.startswith(tenant_prefix):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="FORBIDDEN_STORAGE_KEY",
                message="storage_key does not belong to tenant",
                error_type="packs",
            ),
        )
    settings = get_settings()
    if settings.s3_backend == "minio":
        url = s3.generate_presigned_get_url(normalized_key)
        if url:
            logger.info(
                "packs.download.redirect",
                extra={"tenant": tenant.slug, "storage_key": normalized_key},
            )
            return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    storage = FileStorageService.default()
    payload: bytes | None = None
    try:
        if storage.has(normalized_key):
            payload = storage.get(normalized_key)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=api_problem_detail(
                code="MALFORMED_STORAGE_KEY",
                message="storage_key is malformed",
                error_type="packs",
            ),
        ) from exc

    if payload is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PACK_ARCHIVE_NOT_FOUND",
                message="Archive not found",
                error_type="packs",
            ),
        )
    filename = normalized_key.rsplit("/", 1)[-1] or "package.zip"
    logger.info(
        "packs.download.stream",
        extra={"tenant": tenant.slug, "storage_key": normalized_key, "bytes": len(payload)},
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="download",
        object_type="pack_archive",
        object_id=normalized_key,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"bytes": len(payload)},
    )
    await session.commit()
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
        "Content-Length": str(len(payload)),
    }
    return StreamingResponse(BytesIO(payload), media_type="application/zip", headers=headers)


@router.get("/{pack_id}/download-archive", summary="Download ZIP with pack files")
async def download_pack_files_archive(
    pack_id: str,
    request: Request,
    tenant: TenantDep,
    access: PackReadAccess,
    session: SessionDep,
) -> StreamingResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    files_stmt = select(StoredFile).where(
        StoredFile.tenant_id == tenant.id,
        StoredFile.pack_id == pack_id,
        StoredFile.scan_status == FileScanStatus.CLEAN,
    )
    files = list((await session.scalars(files_stmt)).all())
    if not files:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="PACK_ARCHIVE_NOT_FOUND",
                message="No clean files for this pack",
                error_type="packs",
            ),
        )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            try:
                with s3.stream_object(key=file.storage_key) as stream:
                    content = stream.read()
            except s3.S3OperationError as exc:
                status_code, detail = exc.as_http_detail()
                raise HTTPException(status_code, detail=detail) from exc

            arcname = file.original_name or (file.storage_key.rsplit("/", 1)[-1] or file.id)
            archive.writestr(arcname, content)

    payload = buffer.getvalue()
    headers = {
        "Content-Disposition": f'attachment; filename="pack-{pack_id}.zip"',
        "Content-Length": str(len(payload)),
        "Cache-Control": "no-cache",
    }

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="download",
        object_type="pack_archive",
        object_id=pack_id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"file_count": len(files)},
    )
    await session.commit()

    return StreamingResponse(BytesIO(payload), media_type="application/zip", headers=headers)


@router.get("/{pack_run_id}/safety-summary")
async def pack_safety_summary(
    pack_run_id: str,
    session: SessionDep,
    tenant: TenantDep,
    access: PackReadAccess,
) -> dict[str, list[dict[str, object]]]:
    """Return safety summary for pack run consumers (risk+PPE completeness)."""

    TenantContextValidator.ensure_tenant_context(tenant)

    del access
    tenant_scope = _tenant_scope_values(tenant)

    people_stmt = (
        select(Person)
        .where(Person.tenant_id.in_(tenant_scope), Person.deleted_at.is_(None))
        .limit(100)
    )
    persons = (await session.execute(people_stmt)).scalars().all()

    output: list[dict[str, object]] = []
    for person in persons:
        risk_map_stmt = (
            select(SafetyRiskMap)
            .where(
                SafetyRiskMap.tenant_id.in_(tenant_scope),
                SafetyRiskMap.entity_type == "person",
                SafetyRiskMap.entity_id == person.id,
                SafetyRiskMap.status == "active",
                SafetyRiskMap.deleted_at.is_(None),
            )
            .order_by(SafetyRiskMap.updated_at.desc())
            .limit(1)
        )
        active_risk_map = (await session.execute(risk_map_stmt)).scalar_one_or_none()

        levels: list[str] = []
        if active_risk_map is not None:
            level_stmt = select(RiskMapItem.risk_level).where(
                RiskMapItem.tenant_id.in_(tenant_scope),
                RiskMapItem.risk_map_id == active_risk_map.id,
                RiskMapItem.deleted_at.is_(None),
                RiskMapItem.risk_level.is_not(None),
            )
            raw_levels = [
                str(level) for level in (await session.execute(level_stmt)).scalars().all()
            ]
            rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            levels = sorted(set(raw_levels), key=lambda value: rank.get(value, -1))

        # PPE personal-card lookup removed in СИЗ Срез-1: family-B tables
        # (ppe_personal_cards/...) never had a write path — this always resolved
        # to an empty list. Real personal cards now live at /ppe/employees/{id}/card.
        issued_ppe: list[dict[str, object]] = []

        missing_ppe: dict[str, float] = {}
        has_clearance = PackSafetySummaryService.has_clearance(
            risk_levels=levels, missing_ppe=missing_ppe
        )

        output.append(
            {
                "person_id": person.id,
                "fio": " ".join(
                    filter(None, [person.last_name, person.first_name, person.middle_name])
                ),
                "position": getattr(person.position, "name", None),
                "site": getattr(getattr(person.workplace, "site", None), "name", None),
                "active_risk_map_id": active_risk_map.id if active_risk_map else None,
                "risk_levels": levels,
                "required_ppe": [],
                "issued_ppe": issued_ppe,
                "missing_ppe": [
                    {"ppe_catalog_id": catalog_id, "quantity": quantity}
                    for catalog_id, quantity in missing_ppe.items()
                ],
                "has_clearance": has_clearance,
            }
        )

    return {"pack_run_id": pack_run_id, "persons": output}
