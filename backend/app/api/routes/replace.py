from __future__ import annotations

import csv
import hashlib
import json
from io import BytesIO, StringIO
from typing import Annotated
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.replace.engine import ReplaceOptions, replace_docx_bytes
from app.services.idempotency import IdempotencyService, normalize_idempotency_key

router = APIRouter(prefix="/replace", tags=["replace"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_REPLACE_READ_ROLES = ["admin", "employee"]
_REPLACE_WRITE_ROLES = ["admin", "employee"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    value = getattr(tenant, "id", None)
    return str(value) if value is not None else None


ReaderAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_REPLACE_READ_ROLES, action="read replace reports")
    ),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_REPLACE_WRITE_ROLES,
            action="manage document replace",
        )
    ),
]

_RUNS: dict[str, dict] = {}
_REPORTS: dict[str, dict] = {}
_FILES: dict[str, bytes] = {}


def _replace_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="REPLACE_BAD_REQUEST", message=message, error_type="replace"
        ),
    )


def _replace_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="REPLACE_VALIDATION_ERROR", message=message, error_type="replace"
        ),
    )


class ReplaceOptionsPayload(BaseModel):
    case_sensitive: bool = False
    whole_word: bool = False
    dry_run: bool = True
    regex: bool = False
    ignore_styles: list[str] = Field(default_factory=list)
    ignore_regex: list[str] = Field(default_factory=list)
    max_preview_samples: int = 50
    normalize_runs: bool = True


class ReplaceDiffItem(BaseModel):
    from_text: str = Field(alias="from")
    to_text: str = Field(alias="to")
    part: str
    location: str
    before: str
    after: str
    context: str
    match_count: int


class ReplaceDryRunResponse(BaseModel):
    job_id: str
    report_id: str
    summary: dict
    preview_samples: list[ReplaceDiffItem]


class ReplaceApplyResponse(BaseModel):
    job_id: str
    result_file_id: str
    backup_file_id: str | None = None
    report_id: str


class ReplaceRollbackResponse(BaseModel):
    job_id: str
    restored_file_id: str


class ReplaceReportResponse(BaseModel):
    summary: dict
    rows: list[ReplaceDiffItem]
    total: int


def _parse_map(content: bytes) -> dict[str, str]:
    sample = content.decode("utf-8")
    delimiter = ";" if ";" in sample and "," not in sample.splitlines()[0] else ","
    reader = csv.DictReader(StringIO(sample), delimiter=delimiter)
    data: dict[str, str] = {}
    for row in reader:
        source = str(row.get("from") or "").strip()
        target = str(row.get("to") or "").strip()
        if not source:
            raise _replace_unprocessable("from cannot be empty")
        data[source] = target
    return data


def _to_options(payload: ReplaceOptionsPayload) -> ReplaceOptions:
    return ReplaceOptions(
        case_sensitive=payload.case_sensitive,
        whole_word=payload.whole_word,
        regex=payload.regex,
        normalize_runs=payload.normalize_runs,
        ignore_styles=payload.ignore_styles,
        ignore_regex=payload.ignore_regex,
    )


def _request_hash(
    docx_bytes: bytes,
    replace_map: dict[str, str],
    options: ReplaceOptionsPayload,
    mode: str,
    ref: str = "",
) -> str:
    payload = {
        "docx_sha256": hashlib.sha256(docx_bytes).hexdigest(),
        "map": sorted(replace_map.items()),
        "options": options.model_dump(),
        "mode": mode,
        "ref": ref,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _require_tenant(request: Request) -> None:
    if not request.headers.get("X-Tenant"):
        raise _replace_bad_request("X-Tenant header is required")


async def _load_idempotency_response(
    *,
    key: str | None,
    request: Request,
    request_hash: str,
    session: AsyncSession,
    tenant: Tenant,
    model: type[BaseModel],
) -> tuple[IdempotencyService, object, bool, BaseModel | None]:
    normalized_key = normalize_idempotency_key(key)
    idempotency = IdempotencyService(
        session=session,
        tenant_id=str(tenant.id),
        endpoint=f"{request.method}:{request.url.path}",
    )
    record, created = await idempotency.acquire(
        key=normalized_key,
        request_hash=request_hash,
        method=request.method,
        path=request.url.path,
    )
    if not created:
        cached = await idempotency.respond_from_store(record, model=model)
        return idempotency, record, created, cached
    return idempotency, record, created, None


def _build_report(
    run_id: str, hits: list[dict], mapping: dict[str, str], max_samples: int
) -> tuple[str, dict]:
    by_pair: dict[str, int] = {}
    for source, target in mapping.items():
        by_pair[f"{source}->{target}"] = 0
    for hit in hits:
        by_pair[f"{hit['from']}->{hit['to']}"] = (
            by_pair.get(f"{hit['from']}->{hit['to']}", 0) + hit["match_count"]
        )
    summary = {
        "matches": sum(item["match_count"] for item in hits),
        "files": 1,
        "warnings": [],
        "pairs": by_pair,
    }
    report_id = str(uuid4())
    _REPORTS[report_id] = {"summary": summary, "rows": hits, "job_id": run_id}
    preview = hits[:max_samples]
    return report_id, {"summary": summary, "preview_samples": preview}


@router.post(":dry-run", response_model=ReplaceDryRunResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/dry-run", response_model=ReplaceDryRunResponse, status_code=status.HTTP_202_ACCEPTED)
@audit_operation("dry_run", "document_replace")
async def replace_dry_run(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    options_json: str | None = Header(default=None, alias="X-Replace-Options"),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceDryRunResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    _require_tenant(request)
    if not docx_file or not replace_map:
        raise _replace_bad_request("docx_file and replace_map are required")
    options_payload = (
        ReplaceOptionsPayload.model_validate_json(options_json)
        if options_json
        else ReplaceOptionsPayload()
    )
    docx_bytes = await docx_file.read()
    mapping = _parse_map(await replace_map.read())
    req_hash = _request_hash(docx_bytes, mapping, options_payload, "dry-run")
    idempotency, record, _, cached = await _load_idempotency_response(
        key=_idempotency,
        request=request,
        request_hash=req_hash,
        session=session,
        tenant=tenant,
        model=ReplaceDryRunResponse,
    )
    if cached is not None:
        return cached
    result = replace_docx_bytes(
        docx_bytes, mapping, _to_options(options_payload), apply_changes=False
    )
    run_id = str(uuid4())
    hits = [
        ReplaceDiffItem.model_validate(
            {
                "from": h.from_text,
                "to": h.to_text,
                "part": h.part,
                "location": h.location,
                "before": h.before,
                "after": h.after,
                "context": h.context,
                "match_count": h.match_count,
            }
        ).model_dump(by_alias=True)
        for h in result.hits
    ]
    report_id, data = _build_report(run_id, hits, mapping, options_payload.max_preview_samples)
    _RUNS[run_id] = {"id": run_id, "mode": "dry_run", "report_id": report_id, "status": "succeeded"}
    response = {
        "job_id": run_id,
        "report_id": report_id,
        "summary": data["summary"],
        "preview_samples": data["preview_samples"],
    }
    await idempotency.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=response)
    await session.commit()
    return ReplaceDryRunResponse(**response)


@router.post(":apply", response_model=ReplaceApplyResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/apply", response_model=ReplaceApplyResponse, status_code=status.HTTP_202_ACCEPTED)
@audit_operation("apply", "document_replace")
async def replace_apply(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    backup: bool = Query(True),
    options_json: str | None = Header(default=None, alias="X-Replace-Options"),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceApplyResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    _require_tenant(request)
    if not docx_file or not replace_map:
        raise _replace_bad_request("docx_file and replace_map are required")
    options_payload = (
        ReplaceOptionsPayload.model_validate_json(options_json)
        if options_json
        else ReplaceOptionsPayload(dry_run=False)
    )
    docx_bytes = await docx_file.read()
    mapping = _parse_map(await replace_map.read())
    req_hash = _request_hash(docx_bytes, mapping, options_payload, "apply")
    idempotency, record, _, cached = await _load_idempotency_response(
        key=_idempotency,
        request=request,
        request_hash=req_hash,
        session=session,
        tenant=tenant,
        model=ReplaceApplyResponse,
    )
    if cached is not None:
        return cached
    result = replace_docx_bytes(
        docx_bytes, mapping, _to_options(options_payload), apply_changes=True
    )
    run_id = str(uuid4())
    result_file_id = f"result:{run_id}.docx"
    _FILES[result_file_id] = result.docx_bytes
    backup_file_id = None
    if backup:
        backup_file_id = f"backup:{run_id}.docx"
        _FILES[backup_file_id] = docx_bytes
    hits = [
        ReplaceDiffItem.model_validate(
            {
                "from": h.from_text,
                "to": h.to_text,
                "part": h.part,
                "location": h.location,
                "before": h.before,
                "after": h.after,
                "context": h.context,
                "match_count": h.match_count,
            }
        ).model_dump(by_alias=True)
        for h in result.hits
    ]
    report_id, _ = _build_report(run_id, hits, mapping, options_payload.max_preview_samples)
    _RUNS[run_id] = {
        "id": run_id,
        "mode": "apply",
        "backup_file_id": backup_file_id,
        "result_file_id": result_file_id,
        "report_id": report_id,
        "status": "succeeded",
    }
    response = {
        "job_id": run_id,
        "result_file_id": result_file_id,
        "backup_file_id": backup_file_id,
        "report_id": report_id,
    }
    await idempotency.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=response)
    await session.commit()
    return ReplaceApplyResponse(**response)


@router.post(
    ":rollback", response_model=ReplaceRollbackResponse, status_code=status.HTTP_202_ACCEPTED
)
@router.post(
    "/{replace_run_id}/rollback",
    response_model=ReplaceRollbackResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@audit_operation("rollback", "document_replace")
async def replace_rollback(
    request: Request,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    replace_run_id: str | None = None,
    apply_job_id: str | None = Query(default=None),
    backup_file_id: str | None = Query(default=None),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceRollbackResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    _require_tenant(request)
    target_job = apply_job_id or replace_run_id
    if backup_file_id is None:
        if not target_job or target_job not in _RUNS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
        backup_file_id = _RUNS[target_job].get("backup_file_id")
    if not backup_file_id or backup_file_id not in _FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup file not found")
    req_hash = hashlib.sha256(f"rollback:{target_job}:{backup_file_id}".encode()).hexdigest()
    idempotency, record, _, cached = await _load_idempotency_response(
        key=_idempotency,
        request=request,
        request_hash=req_hash,
        session=session,
        tenant=tenant,
        model=ReplaceRollbackResponse,
    )
    if cached is not None:
        return cached
    run_id = str(uuid4())
    restored_file_id = f"restored:{run_id}.docx"
    _FILES[restored_file_id] = _FILES[backup_file_id]
    _RUNS[run_id] = {
        "id": run_id,
        "mode": "rollback",
        "restored_file_id": restored_file_id,
        "status": "succeeded",
    }
    response = {"job_id": run_id, "restored_file_id": restored_file_id}
    await idempotency.store_success(record, status_code=status.HTTP_202_ACCEPTED, body=response)
    await session.commit()
    return ReplaceRollbackResponse(**response)


@router.get("/reports/{report_id}", response_model=ReplaceReportResponse)
async def get_replace_report(
    report_id: str,
    request: Request,
    _: ReaderAccess,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
) -> ReplaceReportResponse:
    _require_tenant(request)
    report = _REPORTS.get(report_id)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    rows = report["rows"][offset : offset + limit]
    return ReplaceReportResponse(summary=report["summary"], rows=rows, total=len(report["rows"]))


@router.get("/reports/{report_id}.csv")
async def get_replace_report_csv(
    report_id: str,
    request: Request,
    _: ReaderAccess,
) -> StreamingResponse:
    _require_tenant(request)
    report = _REPORTS.get(report_id)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    buff = StringIO()
    writer = csv.DictWriter(
        buff,
        fieldnames=["from", "to", "part", "location", "before", "after", "context", "match_count"],
    )
    writer.writeheader()
    writer.writerows(report["rows"])
    return StreamingResponse(BytesIO(buff.getvalue().encode("utf-8")), media_type="text/csv")


@router.get("/{replace_run_id}/diff")
async def get_replace_diff(
    replace_run_id: str,
    request: Request,
    _: ReaderAccess,
    limit: int = Query(50, ge=1, le=1000),
) -> dict:
    _require_tenant(request)
    run = _RUNS.get(replace_run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    report = _REPORTS.get(run.get("report_id"), {"summary": {}, "rows": []})
    return {"summary": report["summary"], "items": report["rows"][:limit]}
