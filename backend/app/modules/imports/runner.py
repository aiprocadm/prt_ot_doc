"""OPS-71 срез-2 (разд. 71.1): исполнение импорта в фоне с прогрессом.

ТЗ требует «асинхронный импорт больших файлов с прогрессом и отчётом (как
pipeline)». Синхронная ручка упирается в таймаут прокси, поэтому у неё потолок
5000 строк; здесь потолок на порядок выше, а клиенту есть что опрашивать.

**Прогресс обязан коммититься по ходу дела.** Прогресс, видимый только в конце,
— это не прогресс, а два состояния «ничего» и «всё»: незакоммиченную транзакцию
чужая сессия не видит в принципе. Поэтому применение идёт порциями, и каждая
порция фиксируется. Плата за это честная и названа прямо: оборвавшийся импорт
оставляет уже применённые порции. Именно из-за них статус ``failed`` отдельный,
а не «как будто ничего не было», — каждая записанная строка попала в
``import_row`` и снимается штатным откатом партии.

**Файл кладётся в хранилище арендатора.** Воркер живёт в другом процессе, тело
HTTP-запроса ему недоступно. После терминального статуса файл удаляется: это
ПДн, и вторая копия не должна жить дольше необходимого (SEC-66).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.imports import ImportBatch
from app.models.tenanting import Tenant
from app.modules.files import s3
from app.modules.imports.parsers import MAX_ASYNC_IMPORT_ROWS, ImportFileError
from app.modules.imports.quality import run_quality_check_for_batch
from app.services.client_change_signals import record_client_changes_for_batch
from app.modules.imports.registry import get_target
from app.modules.imports.service import ImportMappingError, ImportService
from app.modules.imports.stream import run_streaming

__all__ = [
    "IMPORT_SOURCE_PREFIX",
    "build_source_key",
    "discard_source",
    "execute_import_batch",
    "load_source",
    "store_source",
]

logger = logging.getLogger(__name__)

IMPORT_SOURCE_PREFIX = "imports"

# Сколько ошибочных строк сохранять по итогам ФОНОВОГО сухого прогона.
# Потолок обязателен: файл на 100 000 строк, где сломана каждая, иначе положил бы
# в отчёт 100 000 записей — их всё равно никто не читает, а таблица распухнет.
# Усечение видно в отчёте (``notes.errors_truncated``), молча оно не происходит.
MAX_PREVIEW_ERROR_ROWS = 500


def build_source_key(*, tenant_id: str, batch_id: str, filename: str) -> str:
    """Ключ исходника внутри префикса арендатора (та же раскладка, что у файлов)."""

    safe_name = (filename or "import").replace("..", "_").replace("/", "_")[:120]
    return f"tenants/{tenant_id}/{IMPORT_SOURCE_PREFIX}/{batch_id}/{safe_name}"


def store_source(*, key: str, content: bytes, filename: str) -> None:
    mime = "application/octet-stream"
    if filename.lower().endswith(".csv"):
        mime = "text/csv"
    elif filename.lower().endswith(".json"):
        mime = "application/json"
    s3.put_object(data=content, mime=mime, key=key, size=len(content))


def load_source(key: str) -> bytes:
    chunks = []
    for stream in s3.stream_object(key=key):
        chunks.append(stream.read() if hasattr(stream, "read") else bytes(stream))
    return b"".join(chunks)


def discard_source(key: str | None) -> None:
    """Удалить исходник. Провал удаления не должен ронять импорт."""

    if not key:
        return
    try:
        s3.delete_object(key=key)
    except Exception:  # noqa: BLE001 — исходник вторичен, партия уже в терминале
        logger.warning("imports.source_cleanup_failed", extra={"key": key})


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def execute_import_batch(
    session: AsyncSession,
    tenant: Tenant,
    batch: ImportBatch,
    *,
    content: bytes | None = None,
    chunk_size: int = 200,
) -> ImportBatch:
    """Обработать поставленную партию: pending → running → applied / failed.

    ``content`` передаётся тестами напрямую; в бою файл читается из хранилища по
    ``batch.source_key``. Session commit'ится по ходу — см. модуль-docstring.
    """

    if batch.status != "pending":
        # Повторный запуск задачи (ретрай брокера) не должен применять партию
        # второй раз: дубли строк здесь необратимы.
        return batch

    target = get_target(batch.target)
    if target is None:
        return await _fail(
            session, batch, "import_target_unknown", f"Unknown target {batch.target!r}"
        )

    batch.status = "running"
    await session.commit()

    if batch.mode == "preview":
        return await _run_preview(session, tenant, batch, target, content)

    async def _on_progress(current: ImportBatch) -> None:
        # Порция зафиксирована: и прогресс, и уже применённые строки становятся
        # видимы снаружи. Без commit'а опрос статуса возвращал бы ноль до конца.
        await session.commit()
        _ = current

    try:
        payload = content if content is not None else load_source(batch.source_key or "")
    except Exception as exc:  # noqa: BLE001 — хранилище отдаёт разнородные ошибки
        return await _fail(session, batch, "import_source_unavailable", str(exc)[:500])

    try:
        # Потоком, а не целиком в памяти: файл на сотни тысяч строк не должен
        # существовать в воркере одним списком (см. modules/imports/stream.py).
        service = ImportService(session, tenant)
        summary = await run_streaming(
            service,
            target,
            batch,
            batch.source_filename,
            payload,
            mode="apply",
            overrides=dict(batch.mapping or {}) or None,
            chunk_size=chunk_size,
            on_progress=_on_progress,
            max_rows=MAX_ASYNC_IMPORT_ROWS,
        )
        batch.mapping = dict(summary.mapping)
        batch.notes = {
            **(batch.notes or {}),
            "unmapped_headers": list(summary.unmapped_headers),
            "unknown_references": {k: list(v) for k, v in summary.unknown_references.items()},
        }
    except (ImportFileError, ImportMappingError) as exc:
        code = getattr(exc, "code", "import_rejected")
        return await _fail(session, batch, code, str(exc)[:500])
    except Exception as exc:  # noqa: BLE001 — воркер обязан оставить причину, а не молчать
        logger.exception("imports.batch_failed", extra={"batch_id": batch.id})
        await session.rollback()
        return await _fail(session, batch, "import_failed", str(exc)[:500])

    batch.status = "applied"
    batch.finished_at = _now()
    await session.commit()

    # Разд. 71.3: загруженное сразу проходит проверки качества. Фоновый путь —
    # естественное место для этого: пользователь никого не ждёт, а результат
    # ложится в ту же партию. Провал проверки импорт не отменяет.
    await run_quality_check_for_batch(session, batch)
    await session.commit()

    # Разд. 51.2: та же загрузка — источник сигналов для ленты изменений у
    # обслуживаемого клиента. Как и проверка качества, провалиться она может
    # только молча: партия уже применена и откату по этой причине не подлежит.
    await record_client_changes_for_batch(session, batch)
    await session.commit()

    discard_source(batch.source_key)
    return batch


async def _run_preview(
    session: AsyncSession,
    tenant: Tenant,
    batch: ImportBatch,
    target,
    content: bytes | None,
) -> ImportBatch:
    """Фоновый сухой прогон: план считается, в целевые таблицы НЕ пишем.

    Синхронный dry-run ограничен потолком 5000 строк, поэтому у большого файла
    предпросмотра не было вовсе — оставалось «применить и посмотреть, что вышло».
    Здесь тот же план строится фоном, а его итог живёт в партии.
    """

    try:
        payload = content if content is not None else load_source(batch.source_key or "")
    except Exception as exc:  # noqa: BLE001 — хранилище отдаёт разнородные ошибки
        return await _fail(session, batch, "import_source_unavailable", str(exc)[:500])

    try:
        summary = await run_streaming(
            ImportService(session, tenant),
            target,
            batch,
            batch.source_filename,
            payload,
            mode="preview",
            overrides=dict(batch.mapping or {}) or None,
            max_error_rows=MAX_PREVIEW_ERROR_ROWS,
            max_rows=MAX_ASYNC_IMPORT_ROWS,
        )
    except (ImportFileError, ImportMappingError) as exc:
        code = getattr(exc, "code", "import_rejected")
        return await _fail(session, batch, code, str(exc)[:500])
    except Exception as exc:  # noqa: BLE001 — воркер обязан оставить причину, а не молчать
        logger.exception("imports.preview_failed", extra={"batch_id": batch.id})
        await session.rollback()
        return await _fail(session, batch, "import_failed", str(exc)[:500])

    # Счётчики предпросмотра читаются как «сколько БЫЛО БЫ»: режим партии говорит,
    # что ничего не применялось, а второй набор колонок разъехался бы с первым.
    batch.mapping = dict(summary.mapping)
    batch.notes = {
        "unmapped_headers": list(summary.unmapped_headers),
        "unknown_references": {k: list(v) for k, v in summary.unknown_references.items()},
        "errors_total": summary.errors_total,
        # Усечение обязано быть видно: «показано 500» без пометки читается как
        # «ошибок ровно 500», и остаток обнаружится уже при применении.
        "errors_truncated": summary.errors_total > summary.errors_stored,
    }

    batch.status = "previewed"
    batch.finished_at = _now()
    await session.commit()
    discard_source(batch.source_key)
    return batch


async def _fail(session: AsyncSession, batch: ImportBatch, code: str, message: str) -> ImportBatch:
    batch.status = "failed"
    batch.error_message = f"{code}: {message}"
    batch.finished_at = _now()
    await session.commit()
    discard_source(batch.source_key)
    return batch
