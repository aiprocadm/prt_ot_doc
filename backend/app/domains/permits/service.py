"""Session-aware operations for personal permits (личные допуски)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.permits import lifecycle as lc
from app.models.models import Permit


def _today() -> date:
    return date.today()


async def _get(session: AsyncSession, tenant_id: str, permit_id: str) -> Permit | None:
    stmt = select(Permit).where(Permit.id == permit_id, Permit.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    permit_type: str,
    issued_at: date | None = None,
    valid_until: date | None = None,
    position_id: str | None = None,
) -> Permit:
    """Create a permit. Caller must have validated person/position existence."""
    issued = issued_at or _today()
    status = lc.due_status(lc.PERMIT_STATUS_ACTIVE, valid_until, _today())
    permit = Permit(
        tenant_id=tenant_id,
        person_id=person_id,
        position_id=position_id,
        permit_type=permit_type,
        issued_at=issued,
        valid_until=valid_until,
        status=status,
    )
    session.add(permit)
    await session.flush()
    await session.refresh(permit)
    return permit


async def update_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    permit_id: str,
    permit_type: str | None = None,
    valid_until: date | None = None,
    position_id: str | None = None,
    valid_until_set: bool = False,
    position_id_set: bool = False,
) -> Permit | None:
    """Edit an active permit. None when not found; PermitTransitionError when not active.

    ``*_set`` flags distinguish «field omitted» from «field set to None», so that
    valid_until/position_id can be explicitly cleared.
    """
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    if permit.status != lc.PERMIT_STATUS_ACTIVE:
        raise lc.PermitTransitionError(str(permit.status), "edit")
    if permit_type is not None:
        permit.permit_type = permit_type
    if valid_until_set:
        permit.valid_until = valid_until
    if position_id_set:
        permit.position_id = position_id
    await session.flush()
    await session.refresh(permit)
    return permit


async def extend_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    permit_id: str,
    valid_until: date,
) -> Permit | None:
    """Extend/re-validate a permit. None when not found; revoked -> PermitTransitionError."""
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    # active = plain date update; expired = re-validation; anything else (revoked,
    # unknown) is rejected by the FSM.
    if str(permit.status) not in (lc.PERMIT_STATUS_ACTIVE, lc.PERMIT_STATUS_EXPIRED):
        lc.validate_transition(str(permit.status), lc.PERMIT_STATUS_ACTIVE)  # raises
    permit.valid_until = valid_until
    permit.status = lc.PERMIT_STATUS_ACTIVE
    await session.flush()
    await session.refresh(permit)
    return permit


async def revoke_permit(session: AsyncSession, *, tenant_id: str, permit_id: str) -> Permit | None:
    """Revoke an active permit. None when not found; PermitTransitionError otherwise."""
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    lc.validate_transition(str(permit.status), lc.PERMIT_STATUS_REVOKED)
    permit.status = lc.PERMIT_STATUS_REVOKED
    await session.flush()
    await session.refresh(permit)
    return permit


async def expire_due(session: AsyncSession, *, tenant_id: str | None = None) -> int:
    """Flip overdue active permits to expired. Returns the number updated."""
    today = _today()
    stmt = select(Permit).where(
        Permit.status == lc.PERMIT_STATUS_ACTIVE,
        Permit.valid_until.is_not(None),
        Permit.valid_until < today,
    )
    if tenant_id is not None:
        stmt = stmt.where(Permit.tenant_id == tenant_id)
    permits = (await session.execute(stmt)).scalars().all()
    for permit in permits:
        permit.status = lc.PERMIT_STATUS_EXPIRED
    if permits:
        await session.flush()
    return len(permits)
