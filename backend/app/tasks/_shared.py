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
