"""OPS-71 срез-10 (разд. 71.1): потоковая обработка файла порциями.

Раньше и применение, и фоновый предпросмотр держали ВЕСЬ файл в памяти: парсер
собирал список строк, планировщик — список плана. Это и было единственной
причиной потолка в 100 000 строк: не «мы так решили», а «иначе воркер падал
по OOM на чужом файле».

Здесь файл читается ЛЕНИВО и обрабатывается порциями. В памяти живут: текущая
порция, множество уже встреченных ключей (для поиска дублей сквозь порции) и
счётчики. Плана целиком не существует — и это осознанно: план на миллион строк
никто не читает, а его накопление возвращало бы ту же проблему.

Что обязано работать одинаково с непотоковым путём и закреплено тестами:

* номера строк в отчёте совпадают с номерами в файле (нумерация сквозная);
* дубль во второй порции виден, даже если оригинал был в первой;
* сводка неизвестных значений справочников собирается по всему файлу.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from app.models.imports import ImportBatch, ImportRow
from app.modules.imports.parsers import MAX_ASYNC_IMPORT_ROWS, ParsedFile, open_import_source
from app.modules.imports.planner import build_mapping, build_plan, resolve_rows
from app.modules.imports.profiles import ImportProfile, apply_profile_splits, profile_overrides
from app.modules.imports.registry import ImportTarget
from app.modules.imports.service import ImportMappingError, ImportService, ProgressHook

__all__ = ["StreamSummary", "run_streaming"]

logger = logging.getLogger(__name__)

# Размер порции. Больше — меньше коммитов, но выше пик памяти и грубее прогресс.
DEFAULT_CHUNK = 200


@dataclass
class StreamSummary:
    """Итог потоковой обработки — то, что кладётся в партию."""

    counts: dict[str, int] = field(
        default_factory=lambda: {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
    )
    processed: int = 0
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)
    unknown_references: dict[str, list[str]] = field(default_factory=dict)
    errors_stored: int = 0
    errors_total: int = 0


def _chunks(rows: Iterator[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    chunk: list[dict[str, Any]] = []
    for row in rows:
        chunk.append(row)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


async def run_streaming(
    service: ImportService,
    target: ImportTarget,
    batch: ImportBatch,
    filename: str,
    content: bytes,
    *,
    mode: str = "apply",
    overrides: dict[str, str] | None = None,
    profile: ImportProfile | None = None,
    create_missing: frozenset[str] | None = None,
    chunk_size: int = DEFAULT_CHUNK,
    max_error_rows: int | None = None,
    on_progress: ProgressHook | None = None,
    max_rows: int = MAX_ASYNC_IMPORT_ROWS,
) -> StreamSummary:
    """Прогнать файл порциями. ``mode='preview'`` считает план, ничего не записывая."""

    headers, rows = open_import_source(filename, content, max_rows=max_rows)
    effective_overrides = dict(overrides or {})
    if profile is not None:
        effective_overrides = {**profile_overrides(profile), **effective_overrides}
        # Разбор добавляет колонки, которых в заголовках файла нет — маппинг должен
        # знать о них ДО первой порции, иначе обязательные поля «пропадут».
        for split in profile.splits:
            headers = list(headers) + [p for p in split.parts if p not in headers]

    mapping = build_mapping(target, list(headers), effective_overrides)
    if mapping.missing_required:
        raise ImportMappingError(mapping.missing_required, list(headers))

    summary = StreamSummary(
        mapping=dict(mapping.mapping), unmapped_headers=list(mapping.unmapped_headers)
    )
    table = target.model.__tablename__
    seen_keys: dict[str, int] = {}
    first_row_number = 2

    lookups = await service.load_lookups(target)

    for chunk in _chunks(rows, chunk_size):
        parsed = ParsedFile(headers=list(headers), rows=chunk)
        if profile is not None:
            apply_profile_splits(profile, parsed.rows)

        resolved, unknown = resolve_rows(
            target,
            parsed,
            mapping.mapping,
            lookups,
            seen_keys=seen_keys,
            first_row_number=first_row_number,
        )

        if create_missing and unknown and mode == "apply":
            created = await service._create_missing_references(
                target, resolved, unknown, create_missing
            )
            if created:
                # Справочник пополнился — перечитываем его и пересобираем ПОРЦИЮ:
                # строки, падавшие на unknown_reference, теперь должны пройти.
                lookups = await service.load_lookups(target)
                resolved, unknown = resolve_rows(
                    target,
                    parsed,
                    mapping.mapping,
                    lookups,
                    seen_keys={},
                    first_row_number=first_row_number,
                )
                service._created_references = created

        for lookup, values in unknown.items():
            bucket = summary.unknown_references.setdefault(lookup, [])
            for value in values:
                if value not in bucket:
                    bucket.append(value)

        existing = await service._load_existing(target, [r.values for r in resolved if r.ok])
        plan = build_plan(
            target, resolved, existing, mapping.mapping, mapping.unmapped_headers, unknown
        )

        for planned in plan.rows:
            if mode == "preview":
                key = {"create": "created", "update": "updated", "skip": "skipped"}.get(
                    planned.action, "failed"
                )
                summary.counts[key] += 1
                if planned.action == "error":
                    summary.errors_total += 1
                    if max_error_rows is None or summary.errors_stored < max_error_rows:
                        summary.errors_stored += 1
                        service.session.add(
                            ImportRow(
                                tenant_id=service.tenant.id,
                                batch_id=batch.id,
                                row_number=planned.row_number,
                                action="failed",
                                natural_key=planned.natural_key or None,
                                errors=[
                                    {"code": e.code, "field": e.field, "message": e.message}
                                    for e in planned.errors
                                ],
                                message="; ".join(e.message for e in planned.errors)[:2000],
                            )
                        )
            else:
                outcome = await service._apply_row(target, batch, planned, table)
                summary.counts[outcome] += 1

            summary.processed += 1

        first_row_number += len(chunk)

        batch.processed_rows = summary.processed
        batch.total_rows = summary.processed
        batch.created_count = summary.counts["created"]
        batch.updated_count = summary.counts["updated"]
        batch.skipped_count = summary.counts["skipped"]
        batch.failed_count = summary.counts["failed"]
        if on_progress is not None:
            await on_progress(batch)

    return summary
