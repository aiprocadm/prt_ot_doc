from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.document import DocumentVersion
from app.models.models import Tenant
from app.modules.replace.csv_parser import parse_replace_csv
from app.modules.replace.engine_docx import replace_docx
from app.modules.replace.engine_xml import replace_xml_parts
from app.modules.replace.models import ReplaceMap, ReplaceRun, ReplaceRunStatus
from app.modules.replace.repo import get_replace_map_by_code, get_replace_run, list_replace_maps
from app.modules.replace.report import build_report, to_csv
from app.modules.replace.schemas import (
    ReplaceLaunchRequest,
    ReplaceLaunchResponse,
    ReplaceMapCreate,
    ReplaceMapList,
    ReplaceMapPatch,
    ReplaceMapRead,
    ReplaceRunRead,
)
from app.services.file_storage import FileStorageService

router = APIRouter()


@router.post("/replace-maps", response_model=ReplaceMapRead, status_code=status.HTTP_201_CREATED)
async def create_replace_map(
    payload: str | None = Form(default=None),
    replace_csv: UploadFile | None = File(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> ReplaceMapRead:
    if replace_csv is not None:
        rules = parse_replace_csv(await replace_csv.read())
        data = ReplaceMapCreate(code=replace_csv.filename or uuid4().hex, name=replace_csv.filename or "csv", source_type="csv", rules=rules)
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
async def get_maps(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceMapList:
    return ReplaceMapList(items=[ReplaceMapRead.model_validate(x) for x in await list_replace_maps(session, tenant_id=str(tenant.id))])


@router.get("/replace-maps/{replace_map_id}", response_model=ReplaceMapRead)
async def get_map(replace_map_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceMapRead:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    return ReplaceMapRead.model_validate(row)


@router.patch("/replace-maps/{replace_map_id}", response_model=ReplaceMapRead)
async def patch_map(replace_map_id: str, payload: ReplaceMapPatch, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceMapRead:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return ReplaceMapRead.model_validate(row)


@router.delete("/replace-maps/{replace_map_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map(replace_map_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> Response:
    row = await session.get(ReplaceMap, replace_map_id)
    if row is None or row.tenant_id != str(tenant.id) or row.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    row.deleted_at = datetime.now(tz=timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _resolve_map_id(payload: ReplaceLaunchRequest, row: ReplaceMap | None) -> str:
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace map not found")
    return row.id


async def _launch(document_version_id: str, payload: ReplaceLaunchRequest, mode: str, session: AsyncSession, tenant: Tenant) -> ReplaceLaunchResponse:
    version = await session.get(DocumentVersion, document_version_id)
    if version is None or version.tenant_id != str(tenant.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document version not found")
    replace_map = await session.get(ReplaceMap, payload.replace_map_id) if payload.replace_map_id else await get_replace_map_by_code(session, tenant_id=str(tenant.id), code=str(payload.replace_map_code))
    replace_map_id = _resolve_map_id(payload, replace_map)
    storage = FileStorageService.default()
    source = storage.get(version.file_key)
    rules = replace_map.rules or []
    replaced, hits_docx = replace_docx(source, rules, case_sensitive=payload.options.case_sensitive, whole_word=payload.options.whole_word)
    replaced, hits_xml = replace_xml_parts(replaced, rules, case_sensitive=payload.options.case_sensitive, whole_word=payload.options.whole_word)
    hits = [h.__dict__ for h in hits_docx] + hits_xml
    report = build_report(hits, rules)

    run = ReplaceRun(
        tenant_id=str(tenant.id),
        document_version_id=version.id,
        replace_map_id=replace_map_id,
        mode=mode,
        options=payload.options.model_dump(),
        report_json=report,
        before_file_id=version.file_key,
        after_file_id=None,
        status=ReplaceRunStatus.SUCCEEDED.value,
    )
    if mode == "apply":
        new_key = f"{version.file_key.rsplit('.', 1)[0]}_replace_{uuid4().hex[:8]}.docx"
        storage.put(new_key, replaced, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        run.after_file_id = new_key
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return ReplaceLaunchResponse(job_id=run.id, replace_run_id=run.id, status_url=f"/v1/replace-runs/{run.id}", new_document_version_id=run.after_file_id)


@router.post("/documents/{document_version_id}/replace:dry-run", response_model=ReplaceLaunchResponse)
async def replace_dry_run(document_version_id: str, payload: ReplaceLaunchRequest, _idempotency: str | None = Header(default=None, alias="Idempotency-Key"), session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceLaunchResponse:
    return await _launch(document_version_id, payload, "dry_run", session, tenant)


@router.post("/documents/{document_version_id}/replace:apply", response_model=ReplaceLaunchResponse)
async def replace_apply(document_version_id: str, payload: ReplaceLaunchRequest, _idempotency: str | None = Header(default=None, alias="Idempotency-Key"), session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceLaunchResponse:
    return await _launch(document_version_id, payload, "apply", session, tenant)


@router.post("/replace-runs/{replace_run_id}/rollback", response_model=ReplaceLaunchResponse)
async def replace_rollback(replace_run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceLaunchResponse:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None or run.mode != "apply" or not run.after_file_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Replace run cannot be rolled back")
    rolled_id = f"rollback:{run.before_file_id}"
    return ReplaceLaunchResponse(job_id=replace_run_id, replace_run_id=replace_run_id, new_document_version_id=rolled_id)


@router.get("/replace-runs/{replace_run_id}", response_model=ReplaceRunRead)
async def get_run(replace_run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> ReplaceRunRead:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    return ReplaceRunRead.model_validate(run)


@router.get("/replace-runs/{replace_run_id}/report")
async def get_report(replace_run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    return run.report_json


@router.get("/replace-runs/{replace_run_id}/report.csv")
async def get_report_csv(replace_run_id: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> StreamingResponse:
    run = await get_replace_run(session, tenant_id=str(tenant.id), run_id=replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    content = to_csv(run.report_json)
    return StreamingResponse(BytesIO(content.encode("utf-8")), media_type="text/csv")
