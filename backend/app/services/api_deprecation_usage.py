"""OPS-73 срез-3: запись и выборка использования устаревших поверхностей API.

``record_hit`` — упсерт строки (tenant_slug, path_prefix): кто, когда и сколько
раз живьём (2xx) ходил в устаревшую поверхность. ``usages_to_notify`` — выборка
для периодической задачи уведомлений: активные за окно и не уведомлённые
за интервал. Правила отбора — данные, а не разбросанные if'ы: их проверяет
юнит-тест, их же читает задача.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_deprecation_usage import ApiDeprecationUsage

__all__ = ["record_hit", "usages_to_notify"]

#: Не тревожим арендатора чаще, чем раз в этот интервал.
NOTIFY_MIN_INTERVAL_DAYS = 30
#: Уведомляем только тех, кто реально ходил в устаревшее за это окно.
ACTIVITY_WINDOW_DAYS = 30


async def record_hit(
    session: AsyncSession,
    *,
    tenant_slug: str,
    path_prefix: str,
    when: datetime,
    hits: int = 1,
) -> ApiDeprecationUsage:
    """Упсерт счётчика: новая пара → строка, существующая → +hits и last_seen."""

    row = (
        await session.execute(
            select(ApiDeprecationUsage).where(
                ApiDeprecationUsage.tenant_slug == tenant_slug,
                ApiDeprecationUsage.path_prefix == path_prefix,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = ApiDeprecationUsage(
            tenant_slug=tenant_slug,
            path_prefix=path_prefix,
            first_seen_at=when,
            last_seen_at=when,
            hits_2xx=hits,
        )
        session.add(row)
    else:
        row.hits_2xx += hits
        if when > row.last_seen_at:
            row.last_seen_at = when
    await session.flush()
    return row


async def usages_to_notify(
    session: AsyncSession,
    *,
    now: datetime,
    min_interval_days: int = NOTIFY_MIN_INTERVAL_DAYS,
    activity_window_days: int = ACTIVITY_WINDOW_DAYS,
) -> list[ApiDeprecationUsage]:
    """Кого уведомлять: живая активность за окно + не уведомлён за интервал."""

    activity_floor = now - timedelta(days=activity_window_days)
    notified_floor = now - timedelta(days=min_interval_days)
    rows = (
        (
            await session.execute(
                select(ApiDeprecationUsage).where(
                    ApiDeprecationUsage.hits_2xx > 0,
                    ApiDeprecationUsage.last_seen_at >= activity_floor,
                    (
                        ApiDeprecationUsage.last_notified_at.is_(None)
                        | (ApiDeprecationUsage.last_notified_at < notified_floor)
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
