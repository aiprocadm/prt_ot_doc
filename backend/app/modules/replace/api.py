from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.upload import reject_oversize_upload
from app.core.idempotency import compute_request_hash
from app.models.document import DocumentVersion
from app.models.models import Tenant
from app.modules.replace.csv_parser import parse_replace_csv
from app.modules.replace.models import ReplaceMap, ReplaceRun, ReplaceRunStatus
from app.modules.replace.repo import get_replace_map_by_code, get_replace_run, list_replace_maps
from app.modules.replace.report import to_csv
from app.modules.replace.schemas import (
    ReplaceLaunchRequest,
    ReplaceLaunchResponse,
    ReplaceMapCreate,
    ReplaceMapList,
    ReplaceMapPatch,
    ReplaceMapRead,
    ReplaceRollbackRequest,
    ReplaceRunRead,
)
from app.modules.replace.service import create_document_version_from_bytes, execute_replace
from app.services.audit import AuditService, field_level_diff
from app.services.billing import BillingService
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter()


@router.post("/replace-maps", response_model=ReplaceMapRead, status_code=status.HTTP_201_CREATED)
async def create_replace_map(
    payload: str | None = Form(default=None),
    replace_csv: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceMapRead:
    if replace_csv is not None:
        reject_oversize_upload(
            replace_csv,
            code="REPLACE_MAP_UPLOAD_TOO_LARGE",
            error_type="replace",
            message="Файл карты замен превышает максимальный размер загрузки",
        )
        rules = parse_replace_csv(await replace_csv.read())
        data = ReplaceMapCreate(
            code=replace_csv.filename or "replace_map",
            name=replace_csv.filename or "csv",
            source_type="csv",
            rules=rules,
        )
    elif payload is not None:
        data = ReplaceMapCreate.model_validate_json(payload)
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "payload or replace_csv is required")
    row = ReplaceMap(tenant_id=str(tenant.id), **data.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ReplaceMapRead.model_validate(row)


@router.get("/replace-maps", response_model=ReplaceMapList)
async def get_maps(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
) -> ReplaceMapList:
    return ReplaceMapList(
        items=[
            ReplaceMapRead.model_validate(x)
            for x in await list_replace_maps(session, tenant_id=str(tenant.id))
        ]
    )


@router.get("/replace-maps/{replace_map_id}", response_model=ReplaceMapRead)
async def get_map(
    replace_map_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceMapRead:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    return ReplaceMapRead.model_validate(row)


@router.patch("/replace-maps/{replace_map_id}", response_model=ReplaceMapRead)
async def patch_map(
    replace_map_id: str,
    payload: ReplaceMapPatch,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceMapRead:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return ReplaceMapRead.model_validate(row)


@router.delete(
    "/replace-maps/{replace_map_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None
)
async def delete_map(
    replace_map_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> None:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    row.deleted_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _launch(
    document_version_id: str,
    payload: ReplaceLaunchRequest,
    mode: str,
    session: AsyncSession,
    tenant: Tenant,
    request: Request,
    idempotency_key: str | None,
) -> ReplaceLaunchResponse:
    endpoint = f"replace.{mode}"
    idem = IdempotencyService(session=session, tenant_id=str(tenant.id), endpoint=endpoint)
    idem_key = normalize_idempotency_key(idempotency_key)
    req_hash = compute_request_hash(
        {
            "document_version_id": document_version_id,
            "mode": mode,
            **payload.model_dump(mode="json"),
        }
    )
    record, created = await idem.acquire(
        key=idem_key, request_hash=req_hash, method=request.method.upper(), path=request.url.path
    )
    if not created:
        return await idem.respond_from_store(record, model=ReplaceLaunchResponse)
    if mode == "apply":
        await BillingService(session).assert_allowed(tenant, "documents.generate")

    version = await session.get(DocumentVersion, document_version_id)
    if version is None or version.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")
    replace_map = (
        await session.get(ReplaceMap, payload.replace_map_id)
        if payload.replace_map_id
        else await get_replace_map_by_code(
            session, tenant_id=str(tenant.id), code=str(payload.replace_map_code)
        )
    )
    if replace_map is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")

    storage = FileStorageService.default()
    execution = await execute_replace(
        session=session,
        tenant_id=str(tenant.id),
        source_version=version,
        rules=replace_map.rules or [],
        case_sensitive=payload.options.case_sensitive,
        whole_word=payload.options.whole_word,
        regex_enabled=payload.options.regex_enabled,
        scope=payload.options.scope,
        storage=storage,
        run_id=record.id,
    )

    run = ReplaceRun(
        tenant_id=str(tenant.id),
        document_version_id=version.id,
        replace_map_id=replace_map.id,
        mode=mode,
        options=payload.options.model_dump(),
        report_json=execution.report,
        before_file_id=version.file_id or version.file_key,
        after_file_id=None,
        status=ReplaceRunStatus.SUCCEEDED.value,
    )
    session.add(run)
    await session.flush()

    response = ReplaceLaunchResponse(
        job_id=run.id,
        replace_run_id=run.id,
        status_url=f"/v1/replace-runs/{run.id}",
        report_file_id=execution.report_file.id,
        report_file_key=execution.report_file_key,
        hits_count=execution.hits_count,
        examples=execution.examples,
    )
    if mode == "apply":
        file_row, new_version = await create_document_version_from_bytes(
            session=session,
            tenant_id=str(tenant.id),
            source_version=version,
            content=execution.output_bytes,
            storage=storage,
            key_suffix="replace",
        )
        run.after_file_id = new_version.file_id or new_version.file_key
        response.new_document_version_id = new_version.id
        response.document_id = new_version.document_id
        response.version_number = new_version.version_number
        response.file_id = file_row.id
        response.file_key = file_row.storage_key
        await AuditService(session).log_event(
            tenant_id=str(tenant.id),
            action="replace_apply",
            object_type="DocumentVersion",
            object_id=new_version.id,
            user_id=None,
            ip=request.client.host if request.client else "unknown",
            request_id=getattr(request.state, "trace_id", None),
            changed_fields=field_level_diff(
                {
                    "file_key": version.file_key,
                    "file_id": version.file_id,
                    "version_number": version.version_number,
                },
                {
                    "file_key": new_version.file_key,
                    "file_id": new_version.file_id,
                    "version_number": new_version.version_number,
                },
            ),
            details={"replace_run_id": run.id, "source_document_version_id": version.id},
        )

    await idem.store_success(record, status_code=status.HTTP_200_OK, body=response.model_dump())
    await session.commit()
    await session.refresh(run)
    return response


@router.post(
    "/documents/{document_version_id}/replace:dry-run", response_model=ReplaceLaunchResponse
)
async def replace_dry_run(
    document_version_id: str,
    payload: ReplaceLaunchRequest,
    request: Request,
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceLaunchResponse:
    return await _launch(
        document_version_id, payload, "dry_run", session, tenant, request, _idempotency
    )


@router.post("/documents/{document_version_id}/replace:apply", response_model=ReplaceLaunchResponse)
async def replace_apply(
    document_version_id: str,
    payload: ReplaceLaunchRequest,
    request: Request,
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceLaunchResponse:
    return await _launch(
        document_version_id, payload, "apply", session, tenant, request, _idempotency
    )


@router.post("/replace-runs/{replace_run_id}/rollback", response_model=ReplaceLaunchResponse)
async def replace_rollback(
    replace_run_id: str,
    payload: ReplaceRollbackRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceLaunchResponse:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None or run.mode != "apply":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Replace run cannot be rolled back")

    source_version = await session.get(DocumentVersion, run.document_version_id)
    if source_version is None or source_version.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")

    target_version: DocumentVersion | None = None
    if payload.target_document_version_id:
        target_version = await session.get(DocumentVersion, payload.target_document_version_id)
        if target_version is None or target_version.tenant_id != str(tenant.id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Target document version not found")
    elif payload.rollback_to_version_number is not None:
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == source_version.document_id,
            DocumentVersion.version_number == payload.rollback_to_version_number,
            DocumentVersion.tenant_id == str(tenant.id),
        )
        target_version = (await session.execute(stmt)).scalar_one_or_none()
    if target_version is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "target_document_version_id or rollback_to_version_number is required",
        )
    if target_version.document_id != source_version.document_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Target document version belongs to another document"
        )

    storage = FileStorageService.default()
    restored_bytes = storage.get(target_version.file_key)
    file_row, new_version = await create_document_version_from_bytes(
        session=session,
        tenant_id=str(tenant.id),
        source_version=target_version,
        content=restored_bytes,
        storage=storage,
        key_suffix="rollback",
    )

    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="replace_rollback",
        object_type="DocumentVersion",
        object_id=new_version.id,
        user_id=None,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        changed_fields=field_level_diff(
            {
                "file_key": source_version.file_key,
                "file_id": source_version.file_id,
                "version_number": source_version.version_number,
            },
            {
                "file_key": new_version.file_key,
                "file_id": new_version.file_id,
                "version_number": new_version.version_number,
            },
        ),
        details={"replace_run_id": run.id, "restored_from_version_id": target_version.id},
    )

    await session.commit()
    return ReplaceLaunchResponse(
        job_id=replace_run_id,
        replace_run_id=replace_run_id,
        new_document_version_id=new_version.id,
        restored_from_version_id=target_version.id,
        version_number=new_version.version_number,
        document_id=new_version.document_id,
        file_id=file_row.id,
        file_key=file_row.storage_key,
    )


@router.get("/replace-runs/{replace_run_id}", response_model=ReplaceRunRead)
async def get_run(
    replace_run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceRunRead:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    return ReplaceRunRead.model_validate(run)


@router.get("/replace-runs/{replace_run_id}/report")
async def get_report(
    replace_run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    return run.report_json


@router.get("/replace-runs/{replace_run_id}/report.csv")
async def get_report_csv(
    replace_run_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> StreamingResponse:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    content = to_csv(run.report_json)
    return StreamingResponse(BytesIO(content.encode("utf-8")), media_type="text/csv")
