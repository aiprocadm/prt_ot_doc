"""Shared Celery task helpers — extracted from _core.py (ARCH-4 decomposition).

Home for cross-task helpers so task sub-modules (e.g. app.tasks.domain_ticks)
depend on this leaf module instead of importing back into _core (which would be
a cycle). Re-exported from _core for back-compat (`from app.tasks._core import _run_coroutine`).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from time import perf_counter
from typing import Any, Coroutine, TypeVar

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Tenant

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Shared across document generation (document_jobs) and header/PDF jobs (still in _core).
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _run_coroutine(coro: Coroutine[Any, Any, T]) -> T:
    started = perf_counter()
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("tasks._run_coroutine", extra={"bridge": "asyncio.run"})
        try:
            return asyncio.run(coro)
        finally:
            logger.debug(
                "tasks._run_coroutine.done",
                extra={"bridge": "asyncio.run", "seconds": round(perf_counter() - started, 4)},
            )

    result_holder: dict[str, T] = {}
    error_holder: list[BaseException] = []

    def runner() -> None:
        try:
            result_holder["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive branch
            error_holder.append(exc)

    logger.debug("tasks._run_coroutine", extra={"bridge": "thread_asyncio.run"})
    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    logger.debug(
        "tasks._run_coroutine.done",
        extra={"bridge": "thread_asyncio.run", "seconds": round(perf_counter() - started, 4)},
    )
    if error_holder:
        raise error_holder[0]
    return result_holder["value"]


async def task_module_is_on(session: AsyncSession, tenant_id: str, task_name: str) -> bool:
    """Работает ли обход ``task_name`` у этого арендатора (SEC-63 разд. 63.3).

    Ядровой обход работает всегда. Модульный — только там, где модуль продан:
    иначе после отключения модуля его ночной обход продолжал бы слать письма
    про раздел, которого человек не видит, и писать строки в его базу. Разд.
    63.3 называет это «осиротевшие доступы» и требует, чтобы отключение модуля
    гасило связанные интеграции — вебхуки гасит `_prune_module_webhooks`,
    задачи гасит эта проверка.

    Чей обход — решает реестр ``app/tasks/module_scope.py``, а НЕ разбор имени:
    ``ppe.expiry.tick`` выглядит как модуль «СИЗ», но базовые СИЗ — ядро.
    """

    from app.core.feature_flags import is_module_enabled  # noqa: PLC0415 - цикл импорта
    from app.tasks.module_scope import module_for_task  # noqa: PLC0415 - цикл импорта

    code = module_for_task(task_name)
    if code is None:
        return True
    return await is_module_enabled(session, tenant_id, code)


async def _resolve_task_tenant_scope(
    session: AsyncSession,
    tenant_slug: str,
) -> tuple[str, tuple[str, ...]]:
    tenant_id = str(session.info.get("tenant_id") or "").strip()
    tenant = (
        await session.execute(select(Tenant.id).where(Tenant.slug == tenant_slug).limit(1))
    ).scalar_one_or_none()
    if tenant is None:
        raise ValueError(f"Tenant not found for slug {tenant_slug}")
    resolved_tenant_id = str(tenant)
    if tenant_id and tenant_id != resolved_tenant_id:
        raise ValueError(
            f"Tenant scope mismatch for slug {tenant_slug}: session tenant_id={tenant_id}, resolved tenant_id={resolved_tenant_id}"
        )
    if not tenant_id:
        tenant_id = resolved_tenant_id
    tenant_scope = (tenant_id, tenant_slug) if tenant_id != tenant_slug else (tenant_id,)
    return tenant_id, tenant_scope


# См. матрицу retry vs terminal: docs/stabilization/RETRY_VS_TERMINAL_OUTBOX_CELERY.md
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ClientError,
    SQLAlchemyError,
    OSError,
    asyncio.TimeoutError,
)
