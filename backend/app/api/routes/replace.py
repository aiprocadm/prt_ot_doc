from __future__ import annotations

import csv
from io import StringIO
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.docx import DocxService

router = APIRouter(prefix="/replace", tags=["replace"])

_REPLACE_BACKUPS: dict[str, dict[str, bytes]] = {}


class ReplaceDiffItem(BaseModel):
    source: str
    target: str
    occurrences: int


class ReplaceDryRunResponse(BaseModel):
    items: list[ReplaceDiffItem]
    total_occurrences: int


class ReplaceApplyResponse(BaseModel):
    operation_id: str
    items: list[ReplaceDiffItem]


class ReplaceRollbackResponse(BaseModel):
    operation_id: str
    restored: bool


def _parse_map(content: bytes) -> dict[str, str]:
    reader = csv.DictReader(StringIO(content.decode("utf-8")))
    data: dict[str, str] = {}
    for row in reader:
        source = str(row.get("from") or "").strip()
        target = str(row.get("to") or "").strip()
        if source:
            data[source] = target
    return data


def _build_diff(docx_bytes: bytes, replacements: dict[str, str]) -> list[ReplaceDiffItem]:
    text = docx_bytes.decode("latin-1", errors="ignore")
    items: list[ReplaceDiffItem] = []
    for source, target in replacements.items():
        count = text.count(source)
        if count:
            items.append(ReplaceDiffItem(source=source, target=target, occurrences=count))
    return items


@router.post("/dry-run", response_model=ReplaceDryRunResponse)
async def replace_dry_run(
    docx_file: UploadFile = File(...),
    replace_map: UploadFile = File(...),
) -> ReplaceDryRunResponse:
    if not docx_file.filename or not docx_file.filename.endswith(".docx"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "docx_file must be .docx")
    docx_bytes = await docx_file.read()
    replacements = _parse_map(await replace_map.read())
    items = _build_diff(docx_bytes, replacements)
    return ReplaceDryRunResponse(items=items, total_occurrences=sum(item.occurrences for item in items))


@router.post("/apply", response_model=ReplaceApplyResponse)
async def replace_apply(
    docx_file: UploadFile = File(...),
    replace_map: UploadFile = File(...),
) -> ReplaceApplyResponse:
    docx_bytes = await docx_file.read()
    replacements = _parse_map(await replace_map.read())
    items = _build_diff(docx_bytes, replacements)
    updated = DocxService.mass_replace(docx_bytes, replacements)
    operation_id = uuid4().hex
    _REPLACE_BACKUPS[operation_id] = {"original": docx_bytes, "updated": updated}
    return ReplaceApplyResponse(operation_id=operation_id, items=items)


@router.post("/rollback", response_model=ReplaceRollbackResponse)
async def replace_rollback(operation_id: str) -> ReplaceRollbackResponse:
    restored = operation_id in _REPLACE_BACKUPS
    _REPLACE_BACKUPS.pop(operation_id, None)
    return ReplaceRollbackResponse(operation_id=operation_id, restored=restored)
