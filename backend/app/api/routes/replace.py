from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from uuid import uuid4

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.modules.replace.engine import ReplaceOptions, replace_docx_bytes

router = APIRouter(prefix="/replace", tags=["replace"])

_REPLACE_BACKUPS: dict[str, dict[str, bytes]] = {}
_REPLACE_RUNS: dict[str, dict] = {}
_IDEMPOTENCY: dict[str, tuple[str, str]] = {}


class ReplaceDiffItem(BaseModel):
    path: str
    from_text: str = Field(alias="from")
    to_text: str = Field(alias="to")
    occurrences: int
    context_before: str
    context_after: str
    section: str


class ReplaceDryRunResponse(BaseModel):
    job_id: str
    replace_run_id: str
    status_url: str


class ReplaceApplyResponse(BaseModel):
    job_id: str
    replace_run_id: str
    output_file_id: str


class ReplaceRollbackResponse(BaseModel):
    job_id: str
    replace_run_id: str
    restored_file_id: str


class ReplaceMapInline(BaseModel):
    type: str = "inline"
    pairs: list[dict[str, str]]


class ReplacePayload(BaseModel):
    input_file_id: str | None = None
    map: ReplaceMapInline | None = None
    options: dict = Field(default_factory=dict)


class ReplaceRunStatusResponse(BaseModel):
    status: str
    attempts: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    totals: dict
    report_file_id: str | None = None
    backup_file_id: str | None = None
    output_file_id: str | None = None
    error: dict | None = None


def _parse_map(content: bytes) -> dict[str, str]:
    reader = csv.DictReader(StringIO(content.decode("utf-8")))
    data: dict[str, str] = {}
    for row in reader:
        source = str(row.get("from") or "").strip()
        target = str(row.get("to") or "").strip()
        if source:
            data[source] = target
    return data


def _request_hash(docx_bytes: bytes, replace_map: dict[str, str], options: dict, mode: str) -> str:
    payload = {
        "docx_sha256": hashlib.sha256(docx_bytes).hexdigest(),
        "map": sorted(replace_map.items()),
        "options": options,
        "mode": mode,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _store_run(mode: str, *, output: bytes | None, backup: bytes | None, items: list[ReplaceDiffItem], options: dict) -> dict:
    run_id = str(uuid4())
    now = datetime.now(tz=timezone.utc)
    row = {
        "id": run_id,
        "status": "success",
        "attempts": 1,
        "started_at": now,
        "ended_at": now,
        "totals": {
            "total_hits": sum(item.occurrences for item in items),
            "total_replacements": sum(item.occurrences for item in items),
            "files_scanned": 1,
            "sections_scanned": len({item.section for item in items}),
        },
        "report_file_id": f"report:{run_id}",
        "backup_file_id": f"backup:{run_id}" if backup else None,
        "output_file_id": f"output:{run_id}" if output else None,
        "diff": [item.model_dump(by_alias=True) for item in items],
        "options": options,
        "mode": mode,
        "bytes": output,
        "backup_bytes": backup,
    }
    _REPLACE_RUNS[run_id] = row
    return row


async def _execute_replace(
    *,
    request: Request,
    mode: str,
    docx_file: UploadFile | None,
    replace_map: UploadFile | None,
    idempotency_key: str | None,
) -> tuple[bytes, dict[str, str], dict]:
    if not request.headers.get("X-Tenant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant header is required")
    if docx_file is None or replace_map is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "docx_file and replace_map are required")
    docx_bytes = await docx_file.read()
    mapping = _parse_map(await replace_map.read())
    options = {}
    req_hash = _request_hash(docx_bytes, mapping, options, mode)
    if idempotency_key:
        seen = _IDEMPOTENCY.get(idempotency_key)
        if seen is None:
            _IDEMPOTENCY[idempotency_key] = (req_hash, "")
        elif seen[0] != req_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key already used with different request payload")
    return docx_bytes, mapping, options


@router.post("/dry-run", response_model=ReplaceDryRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_dry_run(
    request: Request,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceDryRunResponse:
    docx_bytes, mapping, options = await _execute_replace(
        request=request,
        mode="dry_run",
        docx_file=docx_file,
        replace_map=replace_map,
        idempotency_key=_idempotency,
    )
    result = replace_docx_bytes(docx_bytes, mapping, ReplaceOptions())
    run = _store_run("dry_run", output=None, backup=None, items=[ReplaceDiffItem.model_validate(item.__dict__) for item in result.items], options=options)
    return ReplaceDryRunResponse(job_id=run["id"], replace_run_id=run["id"], status_url=f"/api/v1/replace/{run['id']}")


@router.post("/apply", response_model=ReplaceApplyResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_apply(
    request: Request,
    docx_file: UploadFile | None = File(default=None),
    replace_map: UploadFile | None = File(default=None),
    _idempotency: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReplaceApplyResponse:
    docx_bytes, mapping, options = await _execute_replace(
        request=request,
        mode="apply",
        docx_file=docx_file,
        replace_map=replace_map,
        idempotency_key=_idempotency,
    )
    result = replace_docx_bytes(docx_bytes, mapping, ReplaceOptions())
    items = [ReplaceDiffItem.model_validate(item.__dict__) for item in result.items]
    run = _store_run("apply", output=result.docx_bytes, backup=docx_bytes, items=items, options=options)
    _REPLACE_BACKUPS[run["id"]] = {"original": docx_bytes, "updated": result.docx_bytes}
    return ReplaceApplyResponse(job_id=run["id"], replace_run_id=run["id"], output_file_id=run["output_file_id"] or "")


@router.post("/{replace_run_id}/rollback", response_model=ReplaceRollbackResponse, status_code=status.HTTP_202_ACCEPTED)
async def replace_rollback(replace_run_id: str, request: Request, _idempotency: str | None = Header(default=None, alias="Idempotency-Key")) -> ReplaceRollbackResponse:
    if not request.headers.get("X-Tenant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant header is required")
    run = _REPLACE_RUNS.get(replace_run_id)
    if run is None or run.get("backup_bytes") is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found or no backup available")
    req_hash = hashlib.sha256(f"rollback:{replace_run_id}".encode()).hexdigest()
    if _idempotency:
        seen = _IDEMPOTENCY.get(_idempotency)
        if seen is None:
            _IDEMPOTENCY[_idempotency] = (req_hash, replace_run_id)
        elif seen[0] != req_hash:
            raise HTTPException(status.HTTP_409_CONFLICT, "Idempotency-Key already used with different request payload")

    rolled = _store_run("rollback", output=run["backup_bytes"], backup=None, items=[], options=run.get("options", {}))
    return ReplaceRollbackResponse(job_id=rolled["id"], replace_run_id=replace_run_id, restored_file_id=rolled["output_file_id"] or "")


@router.get("/{replace_run_id}", response_model=ReplaceRunStatusResponse)
async def get_replace_run(replace_run_id: str, request: Request) -> ReplaceRunStatusResponse:
    if not request.headers.get("X-Tenant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant header is required")
    run = _REPLACE_RUNS.get(replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    return ReplaceRunStatusResponse(**{k: run.get(k) for k in ReplaceRunStatusResponse.model_fields})


@router.get("/{replace_run_id}/diff")
async def get_replace_diff(replace_run_id: str, request: Request, limit: int = Query(50, ge=1, le=1000)) -> dict:
    if not request.headers.get("X-Tenant"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Tenant header is required")
    run = _REPLACE_RUNS.get(replace_run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Replace run not found")
    items = list(run.get("diff", []))[:limit]
    return {"summary": run.get("totals", {}), "items": items}
