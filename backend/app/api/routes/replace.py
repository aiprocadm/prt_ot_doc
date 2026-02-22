from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from io import BytesIO, StringIO
from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.modules.replace.engine import ReplaceOptions, replace_docx_bytes

router = APIRouter(prefix="/replace", tags=["replace"])

_RUNS: dict[str, dict] = {}
_REPORTS: dict[str, dict] = {}
_FILES: dict[str, bytes] = {}
_IDEMPOTENCY: dict[str, tuple[str, dict]] = {}


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
            continue
        data[source] = target
    if any(k == "" for k in data):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "from cannot be empty")
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


def _request_hash(docx_bytes: bytes, replace_map: dict[str, str], options: ReplaceOptionsPayload, mode: str, ref: str = "") -> str:
    payload = {
        "docx_sha256": hashlib.sha256(docx_bytes).hexdigest(),
        "map": sorted(replace_map.items()),
        "options": options.model_dump(),
        "mode": mode,
        "ref": ref,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _require_tenant(request: Request) -> None:
    if not request.headers.get("X-Tenant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant header is required")


def _idem(key: str | None, req_hash: str) -> dict | None:
    if not key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {
                "code": "IDEMPOTENCY_KEY_REQUIRED",
                "type": "idempotency",
                "message": "Idempotency-Key header is required",
            },
        )
    seen = _IDEMPOTENCY.get(key)
    if seen is None:
        return None
    old_hash, response = seen
    if old_hash != req_hash:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "IDEMPOTENCY_CONFLICT", "type": "idempotency", "message": "Idempotency-Key already used with different request payload"})
    return response


def _store_idem(key: str | None, req_hash: str, response: dict) -> None:
    if key:
        _IDEMPOTENCY[key] = (req_hash, response)


def _build_report(run_id: str, hits: list[dict], mapping: dict[str, str], max_samples: int) -> tuple[str, dict]:
    by_pair: dict[str, int] = {}
    for source, target in mapping.items():
        by_pair[f"{source}->{target}"] = 0
    for hit in hits:
        by_pair[f"{hit['from']}->{hit['to']}"] = by_pair.get(f"{hit['from']}->{hit['to']}", 0) + hit["match_count"]
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
async def replace_dry_run(
    request: Request,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    options_json: str | None = Header(default=None, alias="X-Replace-Options"),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceDryRunResponse:
    _require_tenant(request)
    if not docx_file or not replace_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "docx_file and replace_map are required")
    options_payload = ReplaceOptionsPayload.model_validate_json(options_json) if options_json else ReplaceOptionsPayload()
    docx_bytes = await docx_file.read()
    mapping = _parse_map(await replace_map.read())
    req_hash = _request_hash(docx_bytes, mapping, options_payload, "dry-run")
    cached = _idem(_idempotency, req_hash)
    if cached:
        return ReplaceDryRunResponse(**cached)
    result = replace_docx_bytes(docx_bytes, mapping, _to_options(options_payload), apply_changes=False)
    run_id = str(uuid4())
    hits = [ReplaceDiffItem.model_validate({"from": h.from_text, "to": h.to_text, "part": h.part, "location": h.location, "before": h.before, "after": h.after, "context": h.context, "match_count": h.match_count}).model_dump(by_alias=True) for h in result.hits]
    report_id, data = _build_report(run_id, hits, mapping, options_payload.max_preview_samples)
    _RUNS[run_id] = {"id": run_id, "mode": "dry_run", "report_id": report_id, "status": "succeeded"}
    response = {"job_id": run_id, "report_id": report_id, "summary": data["summary"], "preview_samples": data["preview_samples"]}
    _store_idem(_idempotency, req_hash, response)
    return ReplaceDryRunResponse(**response)


@router.post(":apply", response_model=ReplaceApplyResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/apply", response_model=ReplaceApplyResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_apply(
    request: Request,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    backup: bool = Query(True),
    options_json: str | None = Header(default=None, alias="X-Replace-Options"),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceApplyResponse:
    _require_tenant(request)
    if not docx_file or not replace_map:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "docx_file and replace_map are required")
    options_payload = ReplaceOptionsPayload.model_validate_json(options_json) if options_json else ReplaceOptionsPayload(dry_run=False)
    docx_bytes = await docx_file.read()
    mapping = _parse_map(await replace_map.read())
    req_hash = _request_hash(docx_bytes, mapping, options_payload, "apply")
    cached = _idem(_idempotency, req_hash)
    if cached:
        return ReplaceApplyResponse(**cached)
    result = replace_docx_bytes(docx_bytes, mapping, _to_options(options_payload), apply_changes=True)
    run_id = str(uuid4())
    result_file_id = f"result:{run_id}.docx"
    _FILES[result_file_id] = result.docx_bytes
    backup_file_id = None
    if backup:
        backup_file_id = f"backup:{run_id}.docx"
        _FILES[backup_file_id] = docx_bytes
    hits = [ReplaceDiffItem.model_validate({"from": h.from_text, "to": h.to_text, "part": h.part, "location": h.location, "before": h.before, "after": h.after, "context": h.context, "match_count": h.match_count}).model_dump(by_alias=True) for h in result.hits]
    report_id, _ = _build_report(run_id, hits, mapping, options_payload.max_preview_samples)
    _RUNS[run_id] = {"id": run_id, "mode": "apply", "backup_file_id": backup_file_id, "result_file_id": result_file_id, "report_id": report_id, "status": "succeeded"}
    response = {"job_id": run_id, "result_file_id": result_file_id, "backup_file_id": backup_file_id, "report_id": report_id}
    _store_idem(_idempotency, req_hash, response)
    return ReplaceApplyResponse(**response)


@router.post(":rollback", response_model=ReplaceRollbackResponse, status_code=status.HTTP_202_ACCEPTED)
@router.post("/{replace_run_id}/rollback", response_model=ReplaceRollbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_rollback(
    request: Request,
    replace_run_id: str | None = None,
    apply_job_id: str | None = Query(default=None),
    backup_file_id: str | None = Query(default=None),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceRollbackResponse:
    _require_tenant(request)
    target_job = apply_job_id or replace_run_id
    if backup_file_id is None:
        if not target_job or target_job not in _RUNS:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
        backup_file_id = _RUNS[target_job].get("backup_file_id")
    if not backup_file_id or backup_file_id not in _FILES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup file not found")
    req_hash = hashlib.sha256(f"rollback:{target_job}:{backup_file_id}".encode()).hexdigest()
    cached = _idem(_idempotency, req_hash)
    if cached:
        return ReplaceRollbackResponse(**cached)
    run_id = str(uuid4())
    restored_file_id = f"restored:{run_id}.docx"
    _FILES[restored_file_id] = _FILES[backup_file_id]
    _RUNS[run_id] = {"id": run_id, "mode": "rollback", "restored_file_id": restored_file_id, "status": "succeeded"}
    response = {"job_id": run_id, "restored_file_id": restored_file_id}
    _store_idem(_idempotency, req_hash, response)
    return ReplaceRollbackResponse(**response)


@router.get("/reports/{report_id}", response_model=ReplaceReportResponse)
async def get_replace_report(report_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=1000)) -> ReplaceReportResponse:
    _require_tenant(request)
    report = _REPORTS.get(report_id)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    rows = report["rows"][offset : offset + limit]
    return ReplaceReportResponse(summary=report["summary"], rows=rows, total=len(report["rows"]))


@router.get("/reports/{report_id}.csv")
async def get_replace_report_csv(report_id: str, request: Request) -> StreamingResponse:
    _require_tenant(request)
    report = _REPORTS.get(report_id)
    if not report:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    buff = StringIO()
    writer = csv.DictWriter(buff, fieldnames=["from", "to", "part", "location", "before", "after", "context", "match_count"])
    writer.writeheader()
    writer.writerows(report["rows"])
    return StreamingResponse(BytesIO(buff.getvalue().encode("utf-8")), media_type="text/csv")


@router.get("/{replace_run_id}/diff")
async def get_replace_diff(replace_run_id: str, request: Request, limit: int = Query(50, ge=1, le=1000)) -> dict:
    _require_tenant(request)
    run = _RUNS.get(replace_run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    report = _REPORTS.get(run.get("report_id"), {"summary": {}, "rows": []})
    return {"summary": report["summary"], "items": report["rows"][:limit]}
