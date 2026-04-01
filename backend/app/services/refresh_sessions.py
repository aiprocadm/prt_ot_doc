from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RefreshSession


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class RefreshSessionError(Exception):
    reason: str


async def create_refresh_session(
    *,
    session: AsyncSession,
    tenant_id: str,
    user_id: str,
    token_jti: str,
    family_id: str,
    expires_at: datetime,
    parent_jti: str | None = None,
) -> RefreshSession:
    row = RefreshSession(
        tenant_id=tenant_id,
        user_id=user_id,
        token_jti=token_jti,
        family_id=family_id,
        parent_token_jti=parent_jti,
        expires_at=expires_at,
        last_seen_at=_utcnow(),
    )
    session.add(row)
    return row


async def revoke_refresh_family(
    *,
    session: AsyncSession,
    tenant_id: str,
    family_id: str,
    reason: str,
) -> None:
    now = _utcnow()
    await session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.tenant_id == tenant_id,
            RefreshSession.family_id == family_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoke_reason=reason)
    )


async def consume_refresh_session(
    *,
    session: AsyncSession,
    tenant_id: str,
    user_id: str,
    token_jti: str,
    family_id: str,
) -> RefreshSession:
    row = (
        await session.execute(
            select(RefreshSession).where(
                RefreshSession.tenant_id == tenant_id,
                RefreshSession.user_id == user_id,
                RefreshSession.token_jti == token_jti,
                RefreshSession.family_id == family_id,
            )
        )
    ).scalar_one_or_none()

    if row is None:
        raise RefreshSessionError("not_found")

    now = _utcnow()
    if row.revoked_at is not None:
        raise RefreshSessionError("revoked")
    if row.replaced_by_token_jti:
        await revoke_refresh_family(
            session=session,
            tenant_id=tenant_id,
            family_id=family_id,
            reason="reuse-detected",
        )
        raise RefreshSessionError("reused")
    if _as_utc(row.expires_at) <= now:
        raise RefreshSessionError("expired")

    row.last_seen_at = now
    return row


async def revoke_refresh_sessions_for_user(
    *,
    session: AsyncSession,
    tenant_id: str,
    user_id: str,
    reason: str,
) -> None:
    now = _utcnow()
    await session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.tenant_id == tenant_id,
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, revoke_reason=reason)
    )
