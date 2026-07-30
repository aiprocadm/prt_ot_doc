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
from app.modules.imports.registry import get_target
from app.modules.imports.service import ImportMappingError, ImportService

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
        await ImportService(session, tenant).apply(
            target,
            batch.source_filename,
            payload,
            overrides=dict(batch.mapping or {}) or None,
            actor_id=batch.applied_by,
            max_rows=MAX_ASYNC_IMPORT_ROWS,
            batch=batch,
            on_progress=_on_progress,
            chunk_size=chunk_size,
        )
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
    discard_source(batch.source_key)
    return batch


async def _fail(session: AsyncSession, batch: ImportBatch, code: str, message: str) -> ImportBatch:
    batch.status = "failed"
    batch.error_message = f"{code}: {message}"
    batch.finished_at = _now()
    await session.commit()
    discard_source(batch.source_key)
    return batch
