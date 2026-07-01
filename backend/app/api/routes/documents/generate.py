"""Documents API — generate / batch / tasks / status endpoints (ARCH-4 slice 5 split)."""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import (
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.helpers.upload import reject_oversize_upload
from app.api.routes.documents._common import (
    _DEFAULT_DOCUMENT_PIPELINE_PROFILE,
    AccessDep,
    DocGeneratePipelineRequest,
    DocGenerateRequest,
    SessionDep,
    StatusAccessDep,
    TemplateResolveRequest,
    TemplateResolveResponse,
    TenantDep,
    _dispatch_celery_task,
    _documents_bad_request,
    _documents_conflict,
    _documents_not_found,
    _documents_payload_too_large,
    _generate_internal_error_problem,
    router,
)
from app.api.routes.documents._generate_helpers import (
    _apply_naming_pattern,
    _ensure_company,
    _ensure_payload_size,
    _ensure_person,
    _extract_branding_generation_metadata,
    _extract_document_version_id,
    _fetch_template,
    _hash_payload,
    _parse_csv_payload,
    _parse_xlsx_payload,
    _resolve_run,
    _resolve_template_candidates,
)
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.errors import api_problem_detail
from app.core.idempotency import compute_request_hash
from app.core.payload_constraints import PayloadConstraintError, enforce_mapping_constraints
from app.core.rate_limit import generate_per_tenant, ip_tenant_key, limiter
from app.core.security import AccessContext
from app.core.tracing import get_trace_id
from app.models.document import (
    DocumentBatchItem,
    DocumentBatchItemStatus,
    DocumentBatchRun,
    DocumentBatchStatus,
)
from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Tenant,
    User,
)
from app.schemas.document import (
    DocumentBatchRunRead,
    DocumentRead,
    DocumentStatusUpdate,
)
from app.schemas.task import TaskAcceptedResponse, TaskStatusResponse
from app.services.audit import AuditService
from app.services.billing import BillingService
from app.services.document_orchestration import ORCHESTRATION_STATES
from app.services.documents import (
    DocumentNotFoundError,
    DocumentWorkflowService,
    InvalidStatusTransitionError,
)
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator
from app.tasks import generate_document_batch_item_task, generate_document_task

logger = logging.getLogger(__name__)


@router.post("/template:resolve", response_model=TemplateResolveResponse)
async def resolve_template_for_quick_generation(
    payload: TemplateResolveRequest,
    tenant: Tenant = TenantDep,
    session: AsyncSession = SessionDep,
    access: AccessContext = AccessDep,
) -> TemplateResolveResponse:
    access.ensure_tenant_access(tenant.id, action="resolve document template")
    if payload.company_id:
        company = await _ensure_company(session, tenant, payload.company_id)
        if access.role in {"client_admin", "client_user"}:
            access.ensure_company_access(company.id, action="resolve document template")
        if payload.person_id:
            await _ensure_person(session, payload.person_id, company)
    candidates = await _resolve_template_candidates(session=session, tenant=tenant, payload=payload)
    if not candidates:
        raise _documents_not_found(
            code="DOCUMENT_TEMPLATE_NOT_FOUND",
            message="No matching template found for the requested scope/case",
        )
    selected = candidates[0]
    chain = [f"{candidate.scope_level}:{candidate.scope_match}" for candidate in candidates[:4]]
    return TemplateResolveResponse(
        template_id=selected.template_id,
        template_code=selected.template_code,
        template_name=selected.template_name,
        template_version=selected.template_version,
        scope_level=selected.scope_level,
        resolution_chain=chain,
        alternatives=candidates[1:3],
    )


@router.post(
    "/generate",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/documents:generate",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: generate_per_tenant(), key_func=ip_tenant_key)
@audit_operation("generate", "document_task", id_attr="task_id")
async def generate_document(
    payload: DocGenerateRequest | DocGeneratePipelineRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> TaskAcceptedResponse:
    settings = get_settings()
    correlation_id = get_trace_id()
    await BillingService(session).assert_allowed(tenant, "documents.generate")
    engine_payload: dict[str, Any] | None = None
    if isinstance(payload, DocGeneratePipelineRequest):
        template_code = payload.template.code
        template_version = payload.template.version
        options: dict[str, Any] = {}
        if payload.pipeline and payload.pipeline.steps:
            if payload.pipeline.steps.zip:
                options["zip"] = bool(payload.pipeline.steps.zip.get("enabled"))
            if payload.pipeline.steps.apply_headers is not None:
                options["apply_headers"] = dict(payload.pipeline.steps.apply_headers)
            if payload.pipeline.steps.replace is not None:
                options["replace"] = dict(payload.pipeline.steps.replace)
            if payload.pipeline.steps.pdf is not None:
                options["pdf"] = dict(payload.pipeline.steps.pdf)
        engine_payload = {
            "template_code": template_code,
            "template_version": template_version,
            "pipeline_profile_id": (
                payload.pipeline.profile_code
                if payload.pipeline and payload.pipeline.profile_code
                else _DEFAULT_DOCUMENT_PIPELINE_PROFILE
            ),
            "input_source_id": payload.data.file_id if payload.data.type == "file" else None,
            "inline_data": payload.data.payload or {},
            "options": options,
        }
    try:
        payload_for_checks = (
            payload.data
            if isinstance(payload, DocGenerateRequest)
            else (payload.data.payload or {})
        )
        enforce_mapping_constraints(payload_for_checks, field="data")
        _ensure_payload_size(
            payload_for_checks, limit=settings.document_payload_max_bytes, field="data"
        )
    except PayloadConstraintError as exc:
        p_code = (
            "DOCUMENT_PAYLOAD_TOO_LARGE"
            if exc.status_code == 413
            else "DOCUMENT_PAYLOAD_CONSTRAINT"
        )
        raise HTTPException(
            exc.status_code,
            detail=api_problem_detail(code=p_code, message=str(exc), error_type="documents"),
        ) from exc

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
        endpoint="documents.generate",
    )
    record, created_record = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method.upper(),
        path=request.url.path,
    )

    created_run = False
    try:
        if engine_payload is not None or (
            isinstance(payload, DocGenerateRequest)
            and (payload.inline_data is not None or payload.input_source_id is not None)
        ):
            orchestrator = DocumentPipelineOrchestrator(session)
            if engine_payload is None:
                legacy_payload = payload
                engine_payload = {
                    "template_code": legacy_payload.template_code,
                    "template_version": legacy_payload.template_version,
                    "pipeline_profile_id": legacy_payload.pipeline_profile_id
                    or _DEFAULT_DOCUMENT_PIPELINE_PROFILE,
                    "input_source_id": legacy_payload.input_source_id,
                    "inline_data": legacy_payload.inline_data or {},
                    "options": legacy_payload.options or {},
                }
            request_hash = compute_request_hash(
                {
                    "tenant_id": str(tenant.id),
                    "endpoint": "documents.generate",
                    **engine_payload,
                }
            )
            if record.request_hash and record.request_hash != request_hash:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=api_problem_detail(
                        code="IDEMPOTENCY_MISMATCH",
                        message="Idempotency key cannot be reused with a different request payload",
                        error_type="idempotency",
                    ),
                )
            record.request_hash = request_hash
            if created_record:
                job = await orchestrator.start_document_job(
                    tenant_id=str(tenant.id),
                    created_by=getattr(access.user, "id", None),
                    payload=engine_payload,
                    idempotency_key=normalized_key,
                    request_hash=request_hash,
                    correlation_id=correlation_id,
                )
                await orchestrator.run_job(job_id=job.id)
                body = {
                    "task_id": job.id,
                    "job_id": job.id,
                    "correlation_id": job.correlation_id or correlation_id,
                    "status_url": f"/api/v1/jobs/{job.id}",
                    "document_version_id": None,
                }
                await BillingService(session).add_usage(tenant_id=str(tenant.id), docs_generated=1)
                await idempotency.store_success(
                    record, status_code=status.HTTP_202_ACCEPTED, body=body
                )
                await session.commit()
                response.status_code = status.HTTP_202_ACCEPTED
                return TaskAcceptedResponse(**body)
            await session.commit()
            return await idempotency.respond_from_store(
                record, model=TaskAcceptedResponse, response=response
            )

        if not isinstance(payload, DocGenerateRequest):
            raise _documents_bad_request("legacy mode requires old payload shape")

        payload_hash = _hash_payload(payload.data)

        template, template_version = await _fetch_template(
            session,
            tenant,
            template_code=payload.template_code,
            template_id=payload.template_id,
            template_version=payload.template_version,
        )
        company = await _ensure_company(session, tenant, payload.company_id)
        person = await _ensure_person(session, payload.person_id, company)
        current_user: User = access.user
        if access.role in {"client_admin", "client_user"}:
            access.ensure_company_access(company.id, action="generate documents")

        branding_generation = _extract_branding_generation_metadata(payload)

        run, created_run = await _resolve_run(
            session,
            idempotency_key=normalized_key,
            tenant=tenant,
            template=template,
            template_version=template_version,
            company=company,
            person=person,
            payload_hash=payload_hash,
            current_user=current_user,
            context=payload.data,
            correlation_id=correlation_id,
            npa_binding_id=payload.npa_binding_id,
            visible_passport=payload.visible_passport,
        )

        if branding_generation:
            metadata = dict(run.result_metadata or {})
            metadata["branding"] = branding_generation
            run.result_metadata = metadata

        if payload.letterhead is not None:
            metadata = dict(run.result_metadata or {})
            metadata["letterhead"] = payload.letterhead.model_dump(mode="json")
            # DocGenerateRequest has no site_id; single-doc generation derives site downstream.
            metadata["site_id"] = None
            run.result_metadata = metadata

        if created_run:
            audit_service = AuditService(session)
            ip = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent")
            await audit_service.log_event(
                tenant_id=str(tenant.id),
                action="render_start",
                object_type="pipeline_run",
                object_id=run.id,
                user_id=current_user.id,
                ip=ip,
                user_agent=user_agent,
                details={
                    "template_id": template.id,
                    "company_id": company.id,
                    "person_id": person.id if person else None,
                },
            )

        if not created_record:
            document_version_id = _extract_document_version_id(run)
            if document_version_id:
                await idempotency.update_document_version_id(
                    key=normalized_key,
                    document_version_id=document_version_id,
                )
            await session.commit()
            return await idempotency.respond_from_store(
                record, model=TaskAcceptedResponse, response=response
            )

        status_url = f"/api/v1/documents/tasks/{run.id}"
        metadata = run.result_metadata or {}
        result = TaskAcceptedResponse(
            task_id=run.id,
            correlation_id=correlation_id,
            status_url=status_url,
            document_version_id=metadata.get("document_version_id"),
        )
        await BillingService(session).add_usage(tenant_id=str(tenant.id), docs_generated=1)
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
    except Exception:
        logger.exception(
            "documents.generate.unexpected_failure",
            extra={"correlation_id": correlation_id},
        )
        await idempotency.store_failure(
            record,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"detail": _generate_internal_error_problem()},
        )
        await session.commit()
        raise

    if created_run:
        try:
            trace_id = get_trace_id()
            _dispatch_celery_task(
                generate_document_task,
                args=[run.id],
                kwargs={"tenant_slug": tenant.slug},
                task_id=run.id,
                headers={"trace_id": trace_id},
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("documents.generate.dispatch_failed", exc_info=exc)
            stored = await idempotency.get(key=normalized_key)
            if stored is not None:
                await idempotency.store_failure(
                    stored,
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={"detail": _generate_internal_error_problem()},
                )
                await session.commit()
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=_generate_internal_error_problem(),
            ) from exc

    response.status_code = status.HTTP_202_ACCEPTED
    return result


@router.post(
    "/batch",
    response_model=DocumentBatchRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: generate_per_tenant(), key_func=ip_tenant_key)
@audit_operation("batch_generate", "document_batch")
async def generate_document_batch(
    file: UploadFile,
    request: Request,
    response: Response,
    template_code: str | None = Form(default=None),
    template_id: str | None = Form(default=None),
    template_version: int | None = Form(default=None),
    company_id: str | None = Form(default=None),
    naming_pattern: str | None = Form(default=None),
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> DocumentBatchRunRead:
    settings = get_settings()
    reject_oversize_upload(
        file,
        code="DOCUMENT_BATCH_FILE_TOO_LARGE",
        error_type="documents",
        message="Файл пакета превышает максимальный размер загрузки",
        max_bytes=settings.max_upload_size,
    )
    await BillingService(session).assert_allowed(tenant, "documents.generate")
    if template_version is None or not company_id or not template_code:
        raise _documents_bad_request("template_code, template_version and company_id required")

    filename = (file.filename or "").lower()
    if filename.endswith(".csv"):
        rows = _parse_csv_payload(file)
    elif filename.endswith(".xlsx"):
        rows = _parse_xlsx_payload(file)
    else:
        raise _documents_bad_request("Unsupported batch file type")

    if not rows:
        raise _documents_bad_request("Batch file is empty")
    if len(rows) > settings.document_batch_max_rows:
        raise _documents_payload_too_large(
            f"Batch cannot exceed {settings.document_batch_max_rows} documents",
            code="DOCUMENT_BATCH_TOO_MANY_ROWS",
        )

    template, template_version_row = await _fetch_template(
        session,
        tenant,
        template_code=template_code,
        template_id=template_id,
        template_version=template_version,
    )
    company = await _ensure_company(session, tenant, company_id)
    if access.role in {"client_admin", "client_user"}:
        access.ensure_company_access(company.id, action="generate documents")

    current_user: User = access.user
    batch = DocumentBatchRun(
        tenant_id=tenant.id,
        template_id=template.id,
        template_version_id=template_version_row.id,
        company_id=company.id,
        naming_pattern=naming_pattern,
        status=DocumentBatchStatus.RUNNING,
        total=len(rows),
        processed=0,
        succeeded=0,
        failed=0,
        created_by=current_user.id,
        started_at=datetime.now(tz=timezone.utc),
    )
    session.add(batch)
    await session.flush()

    items: list[DocumentBatchItem] = []
    for index, row in enumerate(rows, start=1):
        row_payload = {k: v for k, v in row.items() if k not in {"person_id"}}
        try:
            enforce_mapping_constraints(row_payload, field="data")
            _ensure_payload_size(
                row_payload,
                limit=settings.document_payload_max_bytes,
                field="data",
            )
        except PayloadConstraintError as exc:
            p_code = (
                "DOCUMENT_PAYLOAD_TOO_LARGE"
                if exc.status_code == 413
                else "DOCUMENT_PAYLOAD_CONSTRAINT"
            )
            raise HTTPException(
                exc.status_code,
                detail=api_problem_detail(code=p_code, message=str(exc), error_type="documents"),
            ) from exc
        person_id = row.get("person_id") if isinstance(row, dict) else None
        person = await _ensure_person(session, person_id, company)
        output_name = _apply_naming_pattern(naming_pattern, row_payload, index)
        payload_hash = _hash_payload(row_payload)
        run = PipelineRun(
            tenant_id=tenant.id,
            template_id=template.id,
            template_version_id=template_version_row.id,
            status=PipelineRunStatus.QUEUED,
            context=dict(row_payload),
            idempotency_key=f"batch-{batch.id}-{index}",
            result_metadata={
                "company_id": company.id,
                "person_id": person.id if person else None,
                "initiated_by": current_user.id,
                "payload_hash": payload_hash,
                "batch_id": batch.id,
                "row_index": index,
                "output_name": output_name,
            },
        )
        session.add(run)
        await session.flush()
        item = DocumentBatchItem(
            tenant_id=tenant.id,
            batch_id=batch.id,
            row_index=index,
            payload=row_payload,
            person_id=person.id if person else None,
            output_name=output_name,
            pipeline_run_id=run.id,
            status=DocumentBatchItemStatus.PENDING,
        )
        session.add(item)
        items.append(item)

    await session.commit()

    trace_id = get_trace_id()
    for item in items:
        _dispatch_celery_task(
            generate_document_batch_item_task,
            args=[batch.id, item.id],
            kwargs={"tenant_slug": tenant.slug},
            headers={"trace_id": trace_id},
        )

    return DocumentBatchRunRead(
        id=batch.id,
        status=batch.status.value,
        total=batch.total,
        processed=batch.processed,
        succeeded=batch.succeeded,
        failed=batch.failed,
        items=[
            {
                "id": item.id,
                "row_index": item.row_index,
                "status": item.status.value,
                "output_name": item.output_name,
            }
            for item in items
        ],
    )


@router.get(
    "/batch/{batch_id}",
    response_model=DocumentBatchRunRead,
)
async def get_document_batch(
    batch_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> DocumentBatchRunRead:
    access.ensure_tenant_access(tenant.id, action="read document batch")
    batch = (
        await session.execute(
            select(DocumentBatchRun)
            .where(
                DocumentBatchRun.id == batch_id,
                DocumentBatchRun.tenant_id == str(tenant.id),
            )
            .options(selectinload(DocumentBatchRun.items))
        )
    ).scalar_one_or_none()
    if batch is None:
        raise _documents_not_found(code="DOCUMENT_BATCH_NOT_FOUND", message="Batch not found")
    items = batch.items
    return DocumentBatchRunRead(
        id=batch.id,
        status=batch.status.value,
        total=batch.total,
        processed=batch.processed,
        succeeded=batch.succeeded,
        failed=batch.failed,
        items=[
            {
                "id": item.id,
                "row_index": item.row_index,
                "status": item.status.value,
                "error": item.error,
                "document_id": item.document_id,
                "document_version_id": item.document_version_id,
                "output_name": item.output_name,
            }
            for item in items
        ],
    )


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_generation_task_status(
    task_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = AccessDep,
) -> TaskStatusResponse:
    stmt = select(PipelineRun).where(
        PipelineRun.id == task_id,
        PipelineRun.tenant_id == tenant.id,
    )
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise _documents_not_found(
            code="DOCUMENT_GENERATION_TASK_NOT_FOUND",
            message="Task not found",
        )

    metadata = dict(run.result_metadata or {})
    outputs = dict(run.outputs or {})
    if outputs:
        metadata.setdefault("outputs", outputs)

    pipeline_status = run.status.value if hasattr(run.status, "value") else str(run.status)
    metadata.setdefault("pipeline_status", pipeline_status)
    orchestration = dict(metadata.get("orchestration") or {})
    state = orchestration.get("state")
    if state not in ORCHESTRATION_STATES:
        fallback = "failed" if pipeline_status in {"failed", "error"} else "generated"
        orchestration.setdefault("state", fallback)
        orchestration.setdefault("timeline", [])
    metadata["orchestration"] = orchestration

    document_id = metadata.get("document_id") or outputs.get("document_id")
    document_version_id = metadata.get("document_version_id") or outputs.get("document_version_id")

    return TaskStatusResponse(
        task_id=run.id,
        status=pipeline_status,
        document_id=document_id,
        document_version_id=document_version_id,
        error=str(metadata.get("user_facing_error") or run.error or "") or None,
        metadata=metadata or None,
    )


@router.patch("/{document_id}/status", response_model=DocumentRead)
@audit_operation("change_status", "document")
async def update_document_status(
    document_id: str,
    payload: DocumentStatusUpdate,
    request: Request,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    access: AccessContext = StatusAccessDep,
) -> DocumentRead:
    access.ensure_tenant_access(tenant.id, action="manage document status")
    service = DocumentWorkflowService(session=session)
    document = await service.get_document(document_id=document_id, tenant_id=str(tenant.id))
    access.ensure_abac(
        action="manage document status",
        document_id=document.id,
        document_status=(
            document.status.value if hasattr(document.status, "value") else str(document.status)
        ),
        document_owner_id=document.created_by,
        site_id=document.site_id,
        site_company_id=document.company_id,
    )
    actor_id = getattr(access.user, "id", None)
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
    try:
        document = await service.change_status(
            document_id=document_id,
            tenant_id=str(tenant.id),
            new_status=payload.to,
            actor_id=actor_id,
            ip=ip,
            user_agent=user_agent,
        )
    except DocumentNotFoundError as exc:
        raise _documents_not_found(code="DOCUMENT_NOT_FOUND", message=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        await session.commit()
        raise _documents_conflict(str(exc), code="DOCUMENT_INVALID_STATUS_TRANSITION")

    await session.commit()
    await session.refresh(document)
    return DocumentRead.model_validate(document)
