"""OPS-73 срез-3: уведомления потребителям устаревших поверхностей API.

Разд. 73.2 «Предупреждения»: поверх заголовков ``Deprecation``/``Sunset``
арендатор, который ЖИВЬЁМ ходит в устаревшую поверхность, получает событие
``api.deprecation_notice`` в свои вебхуки — тем же каналом, которым его
интеграция уже потребляет платформу. Троттлинг — ``last_notified_at``
(не чаще раза в ``NOTIFY_MIN_INTERVAL_DAYS``), идемпотентность — ключ
с месяцем: повтор тика в том же месяце дедупится на приёмнике.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_deprecation import deprecation_for_prefix
from app.models.tenanting import Tenant
from app.services.api_deprecation_recorder import drain_pending
from app.services.api_deprecation_usage import usages_to_notify
from app.services.events import EventType
from app.services.outbox import OutboxService

__all__ = ["notify_deprecated_usages"]

logger = logging.getLogger(__name__)


async def notify_deprecated_usages(session: AsyncSession, *, now: datetime) -> int:
    """Уведомить арендаторов с живой активностью на устаревших поверхностях.

    Возвращает число отправленных уведомлений. Строки без адресата (слуг
    без арендатора — сканер/опечатка) или с префиксом, уже убранным из
    реестра, помечаются обработанными БЕЗ события — иначе каждый тик
    выбирал бы их заново.
    """

    await drain_pending(session, now=now)
    rows = await usages_to_notify(session, now=now)
    outbox = OutboxService(session)
    notified = 0
    for row in rows:
        entry = deprecation_for_prefix(row.path_prefix)
        if entry is None:
            row.last_notified_at = now
            continue
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == row.tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            row.last_notified_at = now
            continue
        await outbox.enqueue(
            tenant_id=tenant.id,
            event_type=EventType.API_DEPRECATION_NOTICE.value,
            idempotency_key=(f"api-deprecation:{row.tenant_slug}:{row.path_prefix}:{now:%Y-%m}"),
            payload={
                "tenant_id": tenant.id,
                "path_prefix": row.path_prefix,
                "successor": entry.successor,
                "sunset": entry.sunset.isoformat(),
                "docs_url": entry.docs_url,
                "hits_2xx": row.hits_2xx,
                "last_seen_at": row.last_seen_at.isoformat(),
            },
        )
        row.last_notified_at = now
        notified += 1
        logger.info(
            "api.deprecation_notice.enqueued",
            extra={
                "tenant": row.tenant_slug,
                "path_prefix": row.path_prefix,
                "hits_2xx": row.hits_2xx,
            },
        )
    await session.flush()
    return notified
