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
from app.core.feature_flags import is_module_enabled
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.models.imports import ImportBatch
from app.models.tenant_billing import SavedImportProfile
from app.models.tenanting import Tenant
from app.modules.imports import saved_profiles
from app.modules.imports.parsers import (
    MAX_IMPORT_ROWS,
    SUPPORTED_EXTENSIONS,
    ImportFileError,
)
from app.modules.imports.planner import template_headers
from app.modules.imports.profiles import ImportProfile, detect_profile, get_profile, list_profiles
from app.modules.imports.quality import run_quality_check_for_batch
from app.modules.imports.registry import (
    CREATABLE_LOOKUPS,
    ImportTarget,
    get_target,
    list_targets,
)
from app.modules.imports.runner import build_source_key, discard_source, store_source
from app.modules.imports.service import (
    ImportLookupNotCreatableError,
    ImportMappingError,
    ImportRollbackError,
    ImportService,
)
from app.services.client_change_signals import record_client_changes_for_batch
from app.tasks.import_jobs import run_import_batch_job

router = APIRouter(prefix="/imports", tags=["imports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_FEATURE_CODE = "imports"

# Импорт создаёт и перезаписывает кадровые данные пачками. Это ближе к
# администрированию арендатора, чем к ежедневной работе, поэтому круг узкий.
# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_ROLES = list(screen_roles("imports.manage"))


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
    """Гейт модуля импорта — через реестр (BIZ-61).

    Импорт объявлен ядром (решение владельца 2026-08-08), поэтому умолчание
    здесь «включено». Гейт оставлен, а не выкинут: он остаётся точкой, где
    доступ можно отобрать явной записью, и держит модуль в общем страже
    ``scripts/ci/check_module_gates.py``.

    Раньше тут стояло ``is_feature_enabled(..., default=False)`` с кодом,
    которого не было ни в каталоге, ни в тарифах: строку о выдаче создать было
    нечем, и модуль отвечал «не найдено» ВСЕМ арендаторам — при живом пункте
    меню «Импорт данных».
    """

    if not await is_module_enabled(session, str(tenant.id), _FEATURE_CODE):
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


def _parse_create_missing(raw: str | None) -> frozenset[str]:
    """``create_missing`` — список справочников, которые разрешено дозавести.

    Список, а не булев флаг: «создавать недостающее» звучит безобидно ровно до
    того момента, когда импорт заводит юрлицо из опечатки. Пользователь называет
    справочники поимённо, а реестр решает, какие из них вообще на это годятся.
    """

    if not raw:
        return frozenset()
    items = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = sorted(set(items) - CREATABLE_LOOKUPS)
    if unknown:
        raise _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "IMPORT_LOOKUP_NOT_CREATABLE",
            "These lookups cannot be created from an import: " + ", ".join(unknown),
            creatable_lookups=sorted(CREATABLE_LOOKUPS),
        )
    return frozenset(items)


def _require_profile(code: str | None, target: ImportTarget) -> ImportProfile | None:
    """Профиль источника по коду. Чужой цели профиль не подходит по определению."""

    if not code:
        return None
    profile = get_profile(code)
    if profile is None:
        raise _problem(
            status.HTTP_404_NOT_FOUND, "IMPORT_PROFILE_UNKNOWN", f"Unknown import profile {code!r}"
        )
    if profile.target != target.code:
        # Молча проигнорировать несовпадение нельзя: пользователь думал, что
        # загружает по профилю, а маппинг собрался бы автоопределением.
        raise _problem(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "IMPORT_PROFILE_TARGET_MISMATCH",
            f"Profile {profile.code!r} is for target {profile.target!r}, not {target.code!r}",
        )
    return profile


def _lookup_not_creatable(exc: ImportLookupNotCreatableError) -> HTTPException:
    return _problem(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "IMPORT_LOOKUP_NOT_CREATABLE",
        "These lookups cannot be created from an import: " + ", ".join(exc.lookups),
        creatable_lookups=sorted(CREATABLE_LOOKUPS),
    )


# --- схемы ответов --------------------------------------------------------


class ImportColumnOut(BaseModel):
    field: str
    title: str
    kind: str
    required: bool
    aliases: list[str]
    enum_values: list[str] = Field(default_factory=list)
    lookup: str | None = None
    lookup_creatable: bool = False


class ImportTargetOut(BaseModel):
    code: str
    title: str
    description: str
    natural_keys: list[str]
    columns: list[ImportColumnOut]


class ImportProfileOut(BaseModel):
    code: str
    title: str
    target: str
    source: str
    description: str
    mapping: dict[str, str]
    split_columns: list[str] = Field(default_factory=list)


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
    # Профиль, опознанный по заголовкам файла. Подсказка, а не решение: применён
    # он только если его явно попросили.
    detected_profile: str | None = None
    applied_profile: str | None = None
    counts: dict[str, int]
    mapping: dict[str, str]
    unmapped_headers: list[str]
    unknown_references: dict[str, list[str]]
    rows: list[PlannedRowOut]


class ImportBatchOut(BaseModel):
    id: str
    target: str
    status: str
    mode: str
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
                lookup_creatable=c.lookup_creatable,
            )
            for c in target.columns
        ],
    )


def _profile_out(profile: ImportProfile) -> ImportProfileOut:
    return ImportProfileOut(
        code=profile.code,
        title=profile.title,
        target=profile.target,
        source=profile.source,
        description=profile.description,
        mapping=dict(profile.mapping),
        split_columns=[s.source for s in profile.splits],
    )


def _preview_out(
    target_code: str,
    plan,
    *,
    detected: str | None = None,
    applied: str | None = None,
) -> ImportPreviewOut:
    return ImportPreviewOut(
        target=target_code,
        detected_profile=detected,
        applied_profile=applied,
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
        mode=batch.mode,
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


@router.get("/profiles", response_model=list[ImportProfileOut])
async def list_import_profiles(
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
    target: Annotated[str | None, Query()] = None,
) -> list[ImportProfileOut]:
    """Готовые сценарии переезда (разд. 71.2): 1С, типовые Excel, конкуренты."""

    await _require_enabled(session, tenant)
    return [_profile_out(p) for p in list_profiles(target)]


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
    profile: Annotated[str | None, Form()] = None,
) -> ImportPreviewOut:
    """Показать, что будет создано / обновлено / пропущено — БЕЗ записи в БД.

    Дозаведение справочников здесь не предлагается сознательно: сухой прогон не
    пишет в БД, а создание записи справочника — это запись.
    """

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    content = await _read_upload(file)
    selected = _require_profile(profile, target)
    service = ImportService(session, tenant)
    try:
        plan, _mapping_result, parsed = await service.build(
            target, file.filename or "", content, _parse_overrides(mapping), profile=selected
        )
    except ImportFileError as exc:
        raise _file_error(exc) from exc
    except ImportMappingError as exc:
        raise _mapping_error(exc) from exc

    # Подсказка «похоже на выгрузку 1С» считается ВСЕГДА: она полезна именно
    # тогда, когда пользователь профиль не выбрал.
    detected = detect_profile(target.code, parsed.headers)
    return _preview_out(
        target.code,
        plan,
        detected=detected.code if detected else None,
        applied=selected.code if selected else None,
    )


@router.post("/{target_code}/apply", response_model=ImportApplyOut, status_code=201)
@audit_operation("import.apply", "import_batch")
async def apply_import(
    target_code: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ImportAccess,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
    create_missing: Annotated[str | None, Form()] = None,
    profile: Annotated[str | None, Form()] = None,
) -> ImportApplyOut:
    """Применить импорт: корректные строки записываются, ошибочные откладываются.

    ``create_missing`` — список справочников через запятую, которые разрешено
    дозавести (разд. 71.3). Созданные записи попадают в ту же партию и снимаются
    её откатом: справочная строка, пережившая отмену загрузки, — это мусор,
    который потом никто с этой загрузкой не свяжет.
    """

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
            create_missing=_parse_create_missing(create_missing),
            profile=_require_profile(profile, target),
        )
    except ImportFileError as exc:
        raise _file_error(exc) from exc
    except ImportMappingError as exc:
        raise _mapping_error(exc) from exc
    except ImportLookupNotCreatableError as exc:
        raise _lookup_not_creatable(exc) from exc
    # Разд. 51.2: загрузка кадровых — источник сигналов об изменениях у клиента.
    # После apply, но до commit: сигналы попадают в ту же транзакцию, что и сама
    # партия, иначе бывает лента, ссылающаяся на откатившуюся загрузку.
    await record_client_changes_for_batch(session, batch)
    await session.commit()
    return ImportApplyOut(
        batch=_batch_out(batch),
        preview=_preview_out(target.code, plan, applied=profile or None),
    )


async def _enqueue_batch(
    *,
    session: AsyncSession,
    tenant: Tenant,
    target: ImportTarget,
    access: AccessContext,
    file: UploadFile,
    mapping: str | None,
    mode: str,
) -> ImportBatch:
    """Принять файл и поставить фоновую партию (общее для apply и dry-run).

    **Файл сначала кладётся в хранилище, и только потом ставится задача.**
    Обратный порядок дал бы гонку: воркер успевает взять задачу раньше, чем
    появился файл, и партия падает на ровном месте.
    """

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
    batch.mode = mode
    await session.flush()
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
        # Молчаливый 202 здесь означал бы работу, которая никогда не начнётся, —
        # клиент ждал бы прогресса вечно.
        discard_source(batch.source_key)
        batch.status = "failed"
        batch.error_message = f"import_enqueue_failed: {str(exc)[:400]}"
        await session.commit()
        raise _problem(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "IMPORT_ENQUEUE_FAILED",
            "Import queue is unavailable, the batch was not started",
        ) from exc

    return batch


@router.post("/{target_code}/dry-run-async", response_model=ImportBatchOut, status_code=202)
@audit_operation("import.dry_run_async", "import_batch")
async def dry_run_import_async(
    target_code: str,
    session: SessionDep,
    tenant: TenantDep,
    access: ImportAccess,
    file: Annotated[UploadFile, File()],
    mapping: Annotated[str | None, Form()] = None,
) -> ImportBatchOut:
    """Сухой прогон большого файла в фоне: план считается, в БД ничего не пишется.

    Синхронный `dry-run` ограничен потолком строк, поэтому у большого файла
    предпросмотра не было вовсе — оставалось «применить и посмотреть, что вышло».
    """

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    batch = await _enqueue_batch(
        session=session,
        tenant=tenant,
        target=target,
        access=access,
        file=file,
        mapping=mapping,
        mode="preview",
    )
    return _batch_out(batch)


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
    """

    await _require_enabled(session, tenant)
    target = _require_target(target_code)
    batch = await _enqueue_batch(
        session=session,
        tenant=tenant,
        target=target,
        access=access,
        file=file,
        mapping=mapping,
        mode="apply",
    )
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


@router.get("/batches/{batch_id}/report")
async def download_batch_report(
    batch_id: str, session: SessionDep, tenant: TenantDep, _access: ImportAccess
) -> Response:
    """Отчёт по партии файлом (разд. 71.3: «отчёт … скачиваемый, с привязкой к batch id»).

    CSV, а не XLSX: его открывает и Excel, и всё остальное, а отчёт нужен ровно
    для того, чтобы разослать его тем, кто будет править исходные данные.
    """

    await _require_enabled(session, tenant)
    service = ImportService(session, tenant)
    batch = await service.get_batch(batch_id)
    if batch is None:
        raise _problem(status.HTTP_404_NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "Batch not found")

    rows = await service.list_rows(batch_id)
    buffer = StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Строка", "Действие", "Ключ", "ID записи", "Сообщение"])
    for row in rows:
        writer.writerow(
            [
                # Отрицательные номера — не строки файла, а дозаведённые записи
                # справочников: показываем это словом, а не минусом в отчёте.
                row.row_number if row.row_number > 0 else "справочник",
                row.action,
                row.natural_key or "",
                row.entity_id or "",
                (row.message or "").replace("\n", " "),
            ]
        )

    body = "\ufeff" + buffer.getvalue()  # BOM: иначе Excel ломает кириллицу
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="import_report_{batch.id}.csv"'},
    )


@router.post("/batches/{batch_id}/quality-check", response_model=ImportBatchOut)
async def check_batch_quality(
    batch_id: str, session: SessionDep, tenant: TenantDep, _access: ImportAccess
) -> ImportBatchOut:
    """Прогнать проверки Data Quality по записям партии (разд. 71.3).

    Фоновый импорт делает это сам; ручка нужна синхронному пути. Гонять
    тенант-широкий движок правил ВНУТРИ запроса на применение нельзя: на большом
    арендаторе это секунды сверху к операции, которая и так пишет данные, —
    поэтому проверка вынесена отдельным шагом, а не вшита в `apply`.
    """

    await _require_enabled(session, tenant)
    service = ImportService(session, tenant)
    batch = await service.get_batch(batch_id)
    if batch is None:
        raise _problem(status.HTTP_404_NOT_FOUND, "IMPORT_BATCH_NOT_FOUND", "Batch not found")
    if batch.mode == "preview":
        raise _problem(
            status.HTTP_409_CONFLICT,
            "IMPORT_BATCH_IS_PREVIEW",
            "This batch is a dry run: no data was written, so there is nothing to check",
        )

    await run_quality_check_for_batch(session, batch)
    await session.commit()
    return _batch_out(batch)


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


# ---------------------------------------------------------------------------
# OPS-71 разд. 71.2 (срез-192): профиль, который арендатор заводит из СВОЕГО файла.
# ---------------------------------------------------------------------------
#
# Остаток строки требовал «профили конкурентов» и упирался в образцы их выгрузок.
# Образцы не нужны: у клиента, который переезжает, его выгрузка уже есть. Он
# один раз сопоставляет колонки руками и сохраняет сопоставление профилем.


class SavedProfileIn(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=64)
    #: «поле модели -> заголовок в файле источника».
    mapping: dict[str, str]
    #: «составная колонка -> части»: ФИО -> [фамилия, имя, отчество].
    splits: dict[str, list[str]] = Field(default_factory=dict)
    description: str = ""


class DetectProfileIn(BaseModel):
    target: str = Field(min_length=1, max_length=64)
    headers: list[str] = Field(default_factory=list)


def _saved_out(profile) -> ImportProfileOut:
    return ImportProfileOut(
        code=profile.code,
        title=profile.title,
        target=profile.target,
        source=profile.source,
        description=profile.description,
        mapping=dict(profile.mapping),
        split_columns=[split.source for split in profile.splits],
    )


@router.post("/profiles", response_model=ImportProfileOut, status_code=201)
@audit_operation("import.profile_save", "import_profile")
async def save_import_profile(
    payload: SavedProfileIn,
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
) -> ImportProfileOut:
    """Сохранить своё сопоставление колонок как профиль.

    Подпись файла (по каким заголовкам его узнавать) считается САМА из
    сопоставленных заголовков: просить человека выбрать её вручную значит
    задать вопрос, на который он не знает ответа.
    """

    await _require_enabled(session, tenant)
    draft = saved_profiles.ProfileDraft(
        code=payload.code,
        title=payload.title,
        target=payload.target,
        mapping=payload.mapping,
        splits=payload.splits,
        description=payload.description,
    )
    try:
        saved_profiles.validate_draft(draft, known_targets={t.code for t in list_targets()})
    except saved_profiles.SavedProfileError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="IMPORT_PROFILE_INVALID", message=str(exc), error_type="import"
            ),
        ) from exc

    existing = (
        await session.execute(
            select(SavedImportProfile).where(
                SavedImportProfile.tenant_id == str(tenant.id),
                SavedImportProfile.code == draft.code,
            )
        )
    ).scalar_one_or_none()

    signature = saved_profiles.build_signature(draft.mapping)
    if existing is not None:
        # Повторное сохранение того же кода — правка, а не вторая строка:
        # два профиля с одним кодом сделали бы опознание неопределённым.
        existing.title = draft.title
        existing.target = draft.target
        existing.mapping = dict(draft.mapping)
        existing.splits = dict(draft.splits)
        existing.signature = signature
        existing.description = draft.description or None
        await session.flush()
        return _saved_out(saved_profiles.to_import_profile(existing))

    row = SavedImportProfile(
        tenant_id=str(tenant.id),
        code=draft.code,
        title=draft.title,
        target=draft.target,
        mapping=dict(draft.mapping),
        splits=dict(draft.splits),
        signature=signature,
        description=draft.description or None,
    )
    session.add(row)
    await session.flush()
    return _saved_out(saved_profiles.to_import_profile(row))


@router.post("/profiles/detect", response_model=ImportProfileOut | None)
async def detect_import_profile(
    payload: DetectProfileIn,
    session: SessionDep,
    tenant: TenantDep,
    _access: ImportAccess,
) -> ImportProfileOut | None:
    """Опознать файл по его заголовкам.

    Свои профили сильнее встроенных: арендатор знает свою прошлую систему
    лучше, чем догадка платформы.
    """

    await _require_enabled(session, tenant)
    rows = (
        (
            await session.execute(
                select(SavedImportProfile).where(
                    SavedImportProfile.tenant_id == str(tenant.id),
                    SavedImportProfile.target == payload.target,
                )
            )
        )
        .scalars()
        .all()
    )
    merged = saved_profiles.merge_profiles(
        list_profiles(payload.target),
        [saved_profiles.to_import_profile(row) for row in rows],
    )
    found = saved_profiles.detect(merged, payload.headers)
    return _saved_out(found) if found else None
