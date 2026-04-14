from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentVersion
from app.models.file import File, FileKind, FileScanStatus
from app.modules.replace.engine import ReplaceOptions, replace_docx_bytes
from app.modules.replace.report import build_report
from app.services.file_storage import FileStorageService

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
JSON_CONTENT_TYPE = "application/json"


@dataclass
class ReplaceExecutionResult:
    report: dict
    report_file: File
    report_file_key: str
    hits_count: int
    examples: list[dict]
    output_bytes: bytes


def _make_file_record(
    *,
    tenant_id: str,
    storage_key: str,
    content: bytes,
    mime: str,
    original_name: str,
    kind: FileKind = FileKind.DOCUMENT,
) -> File:
    return File(
        tenant_id=tenant_id,
        storage_key=storage_key,
        bucket="local",
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        mime=mime,
        original_name=original_name,
        meta_json={},
        kind=kind,
        is_quarantined=False,
        scan_status=FileScanStatus.CLEAN,
    )


async def _next_version_number(session: AsyncSession, *, document_id: str) -> int:
    query = select(func.max(DocumentVersion.version_number)).where(DocumentVersion.document_id == document_id)
    max_version = (await session.execute(query)).scalar_one()
    return int(max_version or 0) + 1


async def execute_replace(
    *,
    session: AsyncSession,
    tenant_id: str,
    source_version: DocumentVersion,
    rules: list[dict],
    case_sensitive: bool,
    whole_word: bool,
    regex_enabled: bool,
    scope: list[str] | None,
    storage: FileStorageService,
    run_id: str,
) -> ReplaceExecutionResult:
    started = time.perf_counter()
    source = storage.get(source_version.file_key)
    mapping = {
        str(rule.get("from", "")): str(rule.get("to", ""))
        for rule in rules
        if str(rule.get("from", "")).strip()
    }
    options = ReplaceOptions(
        case_sensitive=case_sensitive,
        whole_word=whole_word,
        regex=regex_enabled,
    )
    result = replace_docx_bytes(source, mapping, options, apply_changes=True)
    replaced = result.docx_bytes
    hits = [h.__dict__ for h in result.hits]
    if scope:
        allowed_parts = set(scope)
        hits = [hit for hit in hits if str(hit.get("part")) in allowed_parts or str(hit.get("part")) == "body" and "body" in allowed_parts]
    report = build_report(hits, rules)
    examples = [
        {
            "path": h.get("location"),
            "before": h.get("before", h.get("before_snippet", "")),
            "after": h.get("after", h.get("after_snippet", "")),
        }
        for h in hits[:20]
    ]
    report_payload = {
        "hits_count": len(hits),
        "examples": examples,
        "report": report,
        "metrics": {"duration_ms": int((time.perf_counter() - started) * 1000), "rules_count": len(mapping)},
    }
    report_bytes = json.dumps(report_payload, ensure_ascii=False).encode("utf-8")
    report_key = f"documents/{source_version.document_id}/replace_report_{run_id}.json"
    storage.put(report_key, report_bytes, content_type=JSON_CONTENT_TYPE)
    report_file = _make_file_record(
        tenant_id=tenant_id,
        storage_key=report_key,
        content=report_bytes,
        mime=JSON_CONTENT_TYPE,
        original_name=f"replace_report_{run_id}.json",
        kind=FileKind.OTHER,
    )
    session.add(report_file)
    await session.flush()

    return ReplaceExecutionResult(
        report=report,
        report_file=report_file,
        report_file_key=report_key,
        hits_count=len(hits),
        examples=examples,
        output_bytes=replaced,
    )


async def create_document_version_from_bytes(
    *,
    session: AsyncSession,
    tenant_id: str,
    source_version: DocumentVersion,
    content: bytes,
    storage: FileStorageService,
    key_suffix: str,
) -> tuple[File, DocumentVersion]:
    new_key = f"documents/{source_version.document_id}/{key_suffix}_{uuid4().hex[:8]}.docx"
    storage.put(new_key, content, content_type=DOCX_CONTENT_TYPE)
    doc_file = _make_file_record(
        tenant_id=tenant_id,
        storage_key=new_key,
        content=content,
        mime=DOCX_CONTENT_TYPE,
        original_name=f"document_{key_suffix}.docx",
    )
    session.add(doc_file)
    await session.flush()

    new_version = DocumentVersion(
        tenant_id=tenant_id,
        document_id=source_version.document_id,
        snapshot_id=source_version.snapshot_id,
        template_version=source_version.template_version,
        data_json=dict(source_version.data_json or {}),
        file_key=new_key,
        file_id=doc_file.id,
        template_version_id=source_version.template_version_id,
        version_number=await _next_version_number(session, document_id=source_version.document_id),
        status=source_version.status,
    )
    session.add(new_version)
    await session.flush()
    return doc_file, new_version
