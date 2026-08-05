"""BIZ-49 срез-10: сессии работы «от имени клиента» — SQL-часть.

Чистые правила (срок, запреты) живут в ``impersonation.py``; здесь только
запросы к базе.

Решение, которое важнее кода: **активной считается последняя НЕзакрытая
сессия, а срок проверяется правилом, а не полем в базе.** Иначе истечение
пришлось бы кому-то записывать — фоновой задаче, которая просыпается ровно
в минуту икс. Такая задача однажды не проснётся, и просроченный контекст
останется живым именно тогда, когда это опаснее всего.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.managed_clients import ManagedClientContextSession

__all__ = ["close_open_sessions", "find_open_session"]


async def find_open_session(
    session: AsyncSession, *, tenant_id: str, user_id: str, client_id: str
) -> ManagedClientContextSession | None:
    """Последняя незакрытая сессия специалиста по этому клиенту."""

    stmt = (
        select(ManagedClientContextSession)
        .where(
            ManagedClientContextSession.tenant_id == tenant_id,
            ManagedClientContextSession.user_id == user_id,
            ManagedClientContextSession.managed_client_id == client_id,
            ManagedClientContextSession.ended_at.is_(None),
        )
        .order_by(ManagedClientContextSession.started_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def close_open_sessions(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str,
    now: datetime,
    reason: str,
) -> list[ManagedClientContextSession]:
    """Закрыть все открытые сессии специалиста. Возвращает закрытые строки."""

    stmt = select(ManagedClientContextSession).where(
        ManagedClientContextSession.tenant_id == tenant_id,
        ManagedClientContextSession.user_id == user_id,
        ManagedClientContextSession.ended_at.is_(None),
    )
    rows = list((await session.execute(stmt)).scalars().all())
    for row in rows:
        row.ended_at = now
        row.ended_reason = reason
    if rows:
        await session.flush()
    return rows
