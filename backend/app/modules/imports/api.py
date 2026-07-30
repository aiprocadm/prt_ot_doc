"""OPS-71 (разд. 71.1): API импорт-фреймворка.

Ручки повторяют путь пользователя, а не структуру кода: посмотреть, что вообще
можно загрузить → скачать пустой шаблон → прогнать файл вхолостую → применить →
посмотреть отчёт → при необходимости откатить партию.

Фича за флагом ``imports`` (default-OFF, разд. 36 vNext): импорт пишет в кадровые
таблицы, и включаться он должен осознанно.
"""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.upload import reject_oversize_upload
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.models.imports import ImportBatch
from app.models.tenanting import Tenant
from app.modules.imports.parsers import (
    MAX_IMPORT_ROWS,
    SUPPORTED_EXTENSIONS,
    ImportFileError,
)
from app.modules.imports.planner import template_headers
from app.modules.imports.registry import ImportTarget, get_target, list_targets
from app.modules.imports.runner import build_source_key, discard_source, store_source
from app.modules.imports.service import (
    ImportMappingError,
    ImportRollbackError,
    ImportService,
)
from app.tasks.import_jobs import run_import_batch_job

router = APIRouter(prefix="/imports", tags=["imports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_FEATURE_CODE = "imports"

# Импорт создаёт и перезаписывает кадровые данные пачками. Это ближе к
# администрированию арендатора, чем к ежедневной работе, поэтому круг узкий.
_ROLES = ["owner", "admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ImportAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_ROLES, action="import tenant data")),
]


def _problem(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    detail = api_problem_detail(code=code, message=message, error_type="imports")
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


async def _require_enabled(session: AsyncSession, tenant: Tenant) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False):
        raise _problem(
            status.HTTP_404_NOT_FOUND,
            "IMPORTS_DISABLED",
            "Import module is not enabled for this tenant",
        )


def _require_target(code: str) -> ImportTarget:
    target = get_target(code)
    if target is None:
        raise _problem(
            status.HTTP_404_NOT_FOUND,
            "IMPORT_TARGET_UNKNOWN",
            f"Unknown import target {code!r}",
        )
    return target


def _parse_overrides(raw: str | None) -> dict[str, str]:
    """``mapping`` из multipart приходит JSON-строкой (файл + поля в одном теле)."""

    if not raw:
        return {}
    import json

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "IMPORT_MAPPING_INVALID",
            "mapping must be a JSON object {model_field: file_header}",
        ) from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "IMPORT_MAPPING_INVALID",
            "mapping must be a JSON object {model_field: file_header}",
        )
    return data


# --- схемы ответов --------------------------------------------------------


class ImportColumnOut(BaseModel):
    field: str
    title: str
    kind: str
    required: bool
    aliases: list[str]
    enum_values: list[str] = Field(default_factory=list)
    lookup: str | None = None


class ImportTargetOut(BaseModel):
    code: str
    title: str
    description: str
    natural_keys: list[str]
    columns: list[ImportColumnOut]


class RowErrorOut(BaseModel):
    code: str
    field: str | None = None
    message: str


class PlannedRowOut(BaseModel):
    row_number: int
    action: str
    natural_key: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    errors: list[RowErrorOut] = Field(default_factory=list)


class ImportPreviewOut(BaseModel):
    target: str
    counts: dict[str, int]
    mapping: dict[str, str]
    unmapped_headers: list[str]
    unknown_references: dict[str, list[str]]
    rows: list[PlannedRowOut]


class ImportBatchOut(BaseModel):
    id: str
    target: str
    status: str
    source_filename: str
    source_format: str
    mapping: dict[str, str]
    notes: dict[str, Any]
    total_rows: int
    processed_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    failed_count: int
    applied_at: datetime
    applied_by: str | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    rolled_back_at: datetime | None = None
    rolled_back_by: str | None = None


class ImportRowOut(BaseModel):
    row_number: int
    action: str
    natural_key: str | None = None
    entity_id: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class ImportApplyOut(BaseModel):
    batch: ImportBatchOut
    preview: ImportPreviewOut


def _target_out(target: ImportTarget) -> ImportTargetOut:
    return ImportTargetOut(
        code=target.code,
        title=target.title,
        description=target.description,
        natural_keys=[k.title for k in target.natural_keys],
        columns=[
            ImportColumnOut(
                field=c.field,
                title=c.title,
                kind=c.kind,
                required=c.required,
                aliases=list(c.aliases),
                enum_values=list(c.enum_values),
                lookup=c.lookup,
            )
            for c in target.columns
        ],
    )


def _preview_out(target_code: str, plan) -> ImportPreviewOut:
    return ImportPreviewOut(
        target=target_code,
        counts=plan.counts(),
        mapping=plan.mapping,
        unmapped_headers=plan.unmapped_headers,
        unknown_references=plan.unknown_references,
        rows=[
            PlannedRowOut(
                row_number=r.row_number,
                action=r.action,
                natural_key=r.natural_key,
                changed_fields=sorted(r.values.keys()) if r.action == "update" else [],
                errors=[
                    RowErrorOut(code=e.code, field=e.field, message=e.message) for e in r.errors
                ],
            )
            for r in plan.rows
        ],
    )


def _batch_out(batch: ImportBatch) -> ImportBatchOut:
    return ImportBatchOut(
        id=batch.id,
        target=batch.target,
        status=batch.status,
        source_filename=batch.source_filename,
        source_format=batch.source_format,
        mapping=dict(batch.mapping or {}),
        notes=dict(batch.notes or {}),
        total_rows=batch.total_rows,
        processed_rows=batch.processed_rows,
        created_count=batch.created_count,
        updated_count=batch.updated_count,
        skipped_count=batch.skipped_count,
        failed_count=batch.failed_count,
        applied_at=batch.applied_at,
        applied_by=batch.applied_by,
        finished_at=batch.finished_at,
        error_message=batch.error_message,
        rolled_back_at=batch.rolled_back_at,
        rolled_back_by=batch.rolled_back_by,
    )


async def _read_upload(file: UploadFile) -> bytes:
    reject_oversize_upload(
        file,
        code="IMPORT_FILE_TOO_LARGE",
        error_type="imports",
        message="Import file exceeds the upload limit",
    )
    content = await file.read()
    if not content:
        raise _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "IMPORT_FILE_EMPTY", "Uploaded file is empty"
        )
    return content


def _file_error(exc: ImportFileError) -> HTTPException:
    return _problem(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        exc.code.upper(),
        exc.message,
        supported_formats=list(SUPPORTED_EXTENSIONS),
        max_rows=MAX_IMPORT_ROWS,
    )


def _mapping_error(exc: ImportMappingError) -> HTTPException:
    return _problem(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "IMPORT_REQUIRED_COLUMNS_MISSING",
        "File is missing required columns: " + ", ".join(exc.missing),
        missing_columns=exc.missing,
        file_headers=exc.headers,
    )


# --- ручки ----------------------------------------------------------------


@router.get("/targets", response_model=list[ImportTargetOut])
async def list_import_targets(
    session: SessionDep, tenant: TenantDep, _access: ImportAccess
) -> list[ImportTargetOut]:
    await _require_enabled(session, tenant)
    return [_target_out(t) for t in list_targets()]


@router.get("/targets/{target_code}/template")
async def download_template(
    target_code: str, session: SessionDep, tenant: TenantDep, _access: ImportAccess
) -> Response:
    """Пустой шаблон с нужными колонками (разд. 71.1).

    CSV, а не XLSX: он открывается и Excel, и всем остальным, а заголовки в нём —
    ровно те же строки, по которым работает автоопределение маппинга. Шаблон и
    распознавание собираются из одного описания цели и не могут разъехаться.
    """

    await _require_enabled(session, tenant)
    target = _require_target(target_code)

    buffer = StringIO()
    csv.writer(buffer).writerow(template_headers(target))
    body = "﻿" + buffer.getvalue()  # BOM: иначе Excel ломает кириллицу
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="import_{target.code}_template.csv"'
        },
    )


@router.post("/{target_code}/dry-run", response_model=ImportPreviewOut)
async def dry_run_import(
    target_code: str,
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportPreviewOut:
    """Показать, что будет создано / обновлено / пропущено — БЕЗ записи в БД."""

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    content = await _read_upload(file)
    service = ImportService(session, tenant)
    try:
        plan, _mapping_result, _parsed = await service.build(
            target, file.filename or "", content, _parse_overrides(mapping)
        )
    except ImportFileError as exc:
        raise _file_error(exc) from exc
    except ImportMappingError as exc:
        raise _mapping_error(exc) from exc
    return _preview_out(target.code, plan)


@router.post("/{target_code}/apply", response_model=ImportApplyOut, status_code=201)
@audit_operation("import.apply", "import_batch")
async def apply_import(
    target_code: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ImportAccess,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportApplyOut:
    """Применить импорт: корректные строки записываются, ошибочные откладываются."""

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    content = await _read_upload(file)
    service = ImportService(session, tenant)
    try:
        batch, plan = await service.apply(
            target,
            file.filename or "",
            content,
            overrides=_parse_overrides(mapping),
            actor_id=getattr(access, "user_id", None),
        )
    except ImportFileError as exc:
        raise _file_error(exc) from exc
    except ImportMappingError as exc:
        raise _mapping_error(exc) from exc
    await session.commit()
    return ImportApplyOut(batch=_batch_out(batch), preview=_preview_out(target.code, plan))


@router.post("/{target_code}/apply-async", response_model=ImportBatchOut, status_code=202)
@audit_operation("import.apply_async", "import_batch")
async def apply_import_async(
    target_code: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ImportAccess,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportBatchOut:
    """Поставить импорт в очередь и вернуть партию для опроса прогресса.

    Отвечает 202 сразу: файл на десятки тысяч строк не укладывается в таймаут
    прокси. Клиент опрашивает `GET /imports/batches/{id}` — там `status`,
    `processed_rows` и `total_rows`.

    **Файл сначала кладётся в хранилище, и только потом ставится задача.**
    Обратный порядок дал бы гонку: воркер успевает взять задачу раньше, чем
    появился файл, и партия падает на ровном месте.
    """

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    content = await _read_upload(file)
    filename = file.filename or "import"
    overrides = _parse_overrides(mapping)

    service = ImportService(session, tenant)
    batch = service.new_batch(
        target,
        filename,
        status="pending",
        actor_id=getattr(access, "user_id", None),
    )
    await session.flush()
    # Схема маппинга едет с партией: воркер получает ровно то, что выбрал
    # пользователь, а не догадывается по заголовкам заново.
    batch.mapping = dict(overrides)
    batch.source_key = build_source_key(
        tenant_id=str(tenant.id), batch_id=batch.id, filename=filename
    )

    try:
        store_source(key=batch.source_key, content=content, filename=filename)
    except Exception as exc:  # noqa: BLE001 — хранилище отдаёт разнородные ошибки
        await session.rollback()
        raise _problem(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "IMPORT_SOURCE_STORE_FAILED",
            "Could not store the uploaded file for background processing",
        ) from exc

    await session.commit()

    try:
        run_import_batch_job.delay(tenant.slug, batch.id)
    except Exception as exc:  # noqa: BLE001 — брокер недоступен
        # Партия осталась в ``pending`` и файл в хранилище: её подберёт повторная
        # постановка. Молчаливый 202 здесь означал бы импорт, который никогда не
        # начнётся, — клиент ждал бы прогресса вечно.
        discard_source(batch.source_key)
        batch.status = "failed"
        batch.error_message = f"import_enqueue_failed: {str(exc)[:400]}"
        await session.commit()
        raise _problem(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "IMPORT_ENQUEUE_FAILED",
            "Import queue is unavailable, the batch was not started",
        ) from exc

    return _batch_out(batch)


@router.get("/batches", response_model=list[ImportBatchOut])
async def list_batches(
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
    target: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ImportBatchOut]:
    await _require_enabled(session, tenant)
    stmt = select(ImportBatch).where(ImportBatch.tenant_id == tenant.id)
    if target:
        stmt = stmt.where(ImportBatch.target == target)
    stmt = stmt.order_by(ImportBatch.applied_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_batch_out(b) for b in rows]


@router.get("/batches/{batch_id}", response_model=ImportBatchOut)
async def get_batch(
    batch_id: str, session: SessionDep, tenant: TenantDep, _access: ImportAccess
) -> ImportBatchOut:
    await _require_enabled(session, tenant)
    batch = await ImportService(session, tenant).get_batch(batch_id)
    if batch is None:
        raise _problem(status.HTTP_404_NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "Batch not found")
    return _batch_out(batch)


@router.get("/batches/{batch_id}/rows", response_model=list[ImportRowOut])
async def get_batch_rows(
    batch_id: str,
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
    action: Annotated[str | None, Query()] = None,
) -> list[ImportRowOut]:
    """Построчный отчёт партии. ``action=failed`` — «на исправление»."""

    await _require_enabled(session, tenant)
    service = ImportService(session, tenant)
    batch = await service.get_batch(batch_id)
    if batch is None:
        raise _problem(status.HTTP_404_NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "Batch not found")
    rows = await service.list_rows(batch_id, action)
    return [
        ImportRowOut(
            row_number=r.row_number,
            action=r.action,
            natural_key=r.natural_key,
            entity_id=r.entity_id,
            errors=list(r.errors or []),
            message=r.message,
        )
        for r in rows
    ]


@router.post("/batches/{batch_id}/rollback", response_model=ImportBatchOut)
@audit_operation("import.rollback", "import_batch")
async def rollback_batch(
    batch_id: str, session: SessionDep, tenant: TenantDep, access: ImportAccess
) -> ImportBatchOut:
    """Отменить партию целиком: удалить созданное, вернуть перезаписанное."""

    await _require_enabled(session, tenant)
    service = ImportService(session, tenant)
    batch = await service.get_batch(batch_id)
    if batch is None:
        raise _problem(status.HTTP_404_NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "Batch not found")
    try:
        batch = await service.rollback(batch, actor_id=getattr(access, "user_id", None))
    except ImportRollbackError as exc:
        await session.rollback()
        raise _problem(status.HTTP_409_CONFLICT, exc.code.upper(), str(exc)) from exc
    await session.commit()
    return _batch_out(batch)
