"""OPS-73 срез-3: батч-рекордер обращений к устаревшим поверхностям API.

Middleware зовёт ``note_deprecated_hit`` на каждый 2xx-ответ устаревшей
поверхности; писать БД на каждый запрос нельзя (write-амплификация на горячем
пути). Поэтому хиты копятся в памяти процесса, а в БД уходят порцией — либо
отложенной фоновой задачей (``_schedule_flush``), либо явным ``drain_pending``
(его же зовут тесты и периодическая задача уведомлений — чтобы читать свежее).

Потеря порции при аварийной остановке процесса допустима осознанно: это
эксплуатационная статистика, а не бизнес-данные.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.api_deprecation_usage import record_hit

__all__ = ["note_deprecated_hit", "drain_pending", "reset_for_tests"]

logger = logging.getLogger(__name__)

#: Задержка перед фоновым сливом накопленной порции.
FLUSH_DELAY_S = 5.0

_pending: dict[tuple[str, str], int] = {}
_flush_scheduled = False


def note_deprecated_hit(tenant_slug: str, path_prefix: str) -> None:
    """Учесть 2xx-обращение (в память); слив в БД — отложенно, порцией."""

    global _flush_scheduled
    key = (tenant_slug, path_prefix)
    _pending[key] = _pending.get(key, 0) + 1
    if not _flush_scheduled:
        _flush_scheduled = True
        _schedule_flush()


def _schedule_flush() -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Вне event loop (синхронный тест/скрипт) — порция дождётся drain_pending.
        return
    loop.create_task(_flush_after_delay())


async def _flush_after_delay() -> None:
    await asyncio.sleep(FLUSH_DELAY_S)
    # Импорт здесь: модуль сессий тянет настройки, а рекордер импортируется
    # middleware'ом на старте приложения — не заставляем его платить за это.
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            await drain_pending(session, now=datetime.now(tz=timezone.utc))
            await session.commit()
    except Exception:  # статистика не должна ронять приложение
        logger.warning("api-deprecation usage flush failed", exc_info=True)


async def drain_pending(session: AsyncSession, *, now: datetime) -> int:
    """Слить накопленное упсертами. Возвращает число записанных пар."""

    global _flush_scheduled
    batch = dict(_pending)
    _pending.clear()
    _flush_scheduled = False
    for (tenant_slug, path_prefix), hits in batch.items():
        await record_hit(
            session,
            tenant_slug=tenant_slug,
            path_prefix=path_prefix,
            when=now,
            hits=hits,
        )
    return len(batch)


def reset_for_tests() -> None:
    global _flush_scheduled
    _pending.clear()
    _flush_scheduled = False
