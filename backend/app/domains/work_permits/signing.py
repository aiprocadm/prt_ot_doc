"""Подписи ПЭП наряда-допуска (Ф2): тонкая обёртка над PepSigningService.

Подход A — без промежуточной таблицы: подписи живут в signature_requests.
Два потока: наряд (ответственные роли) и целевой инструктаж (бригада).
Валидирует членство и блокирует повторную подпись (create_attested сам этого
не делает; create_request блокирует только активные дубли, не SIGNED).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.work_permits.lifecycle import CLOSING_SIGNER_ROLES
from app.domains.work_permits.service import get_briefing
from app.models.models import SignatureRequest
from app.models.work_permit import WorkPermitMember
from app.services.pep_signing import PepConflict, PepNotFound, PepSigningService

PERMIT_SIGNER_ROLES = frozenset({"issuer", "supervisor", "admitter", "foreman"})
BRIEFING_SIGNER_ROLES = frozenset({"member", "observer", "foreman"})
_SIGN_MODES = frozenset({"attested", "code"})
_SIGNED = "signed"


class WorkPermitSignerError(PepConflict):
    """Подписант не входит в нужный класс ролей наряда (маппится в 409)."""


async def _member_role(
    session: AsyncSession,
    *,
    tenant_id: str,
    work_permit_id: str,
    person_id: str,
    allowed_roles: frozenset[str],
) -> str | None:
    stmt = select(WorkPermitMember.role).where(
        WorkPermitMember.tenant_id == tenant_id,
        WorkPermitMember.work_permit_id == work_permit_id,
        WorkPermitMember.person_id == person_id,
        WorkPermitMember.role.in_(tuple(allowed_roles)),
    )
    return (await session.execute(stmt)).scalars().first()


async def _reject_if_signed(
    session: AsyncSession,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    signer_person_id: str,
) -> None:
    stmt = select(SignatureRequest.id).where(
        SignatureRequest.tenant_id == tenant_id,
        SignatureRequest.object_type == object_type,
        SignatureRequest.object_id == object_id,
        SignatureRequest.signer_person_id == signer_person_id,
        SignatureRequest.status == _SIGNED,
    )
    if (await session.execute(stmt)).scalars().first() is not None:
        raise PepConflict("already signed by this person")


async def _dispatch(
    session: AsyncSession,
    *,
    tenant_id: str,
    object_type: str,
    object_id: str,
    purpose: str,
    person_id: str,
    mode: str,
    requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    if mode not in _SIGN_MODES:
        raise PepConflict(f"unsupported mode: {mode}")
    await _reject_if_signed(
        session,
        tenant_id=tenant_id,
        object_type=object_type,
        object_id=object_id,
        signer_person_id=person_id,
    )
    svc = PepSigningService(session, tenant_id)
    if mode == "attested":
        req = await svc.create_attested(
            object_type=object_type,
            object_id=object_id,
            purpose=purpose,
            requested_by=requested_by,
            signer_person_id=person_id,
        )
        return req, None
    return await svc.create_request(
        object_type=object_type,
        object_id=object_id,
        purpose=purpose,
        requested_by=requested_by,
        signer_person_id=person_id,
    )


async def sign_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    work_permit_id: str,
    person_id: str,
    mode: str,
    requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    role = await _member_role(
        session,
        tenant_id=tenant_id,
        work_permit_id=work_permit_id,
        person_id=person_id,
        allowed_roles=PERMIT_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a responsible member of this permit")
    return await _dispatch(
        session,
        tenant_id=tenant_id,
        object_type="work_permit",
        object_id=work_permit_id,
        purpose="work_permit",
        person_id=person_id,
        mode=mode,
        requested_by=requested_by,
    )


async def sign_briefing(
    session: AsyncSession,
    *,
    tenant_id: str,
    briefing_id: str,
    person_id: str,
    mode: str,
    requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    br = await get_briefing(session, tenant_id=tenant_id, briefing_id=briefing_id)
    if br is None:
        raise PepNotFound("work_permit_briefing")
    role = await _member_role(
        session,
        tenant_id=tenant_id,
        work_permit_id=br.work_permit_id,
        person_id=person_id,
        allowed_roles=BRIEFING_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a brigade member of this permit")
    return await _dispatch(
        session,
        tenant_id=tenant_id,
        object_type="work_permit_briefing",
        object_id=briefing_id,
        purpose="work_permit_briefing",
        person_id=person_id,
        mode=mode,
        requested_by=requested_by,
    )


async def sign_closing(
    session: AsyncSession,
    *,
    tenant_id: str,
    work_permit_id: str,
    person_id: str,
    mode: str,
    requested_by: str,
) -> tuple[SignatureRequest, str | None]:
    """Подпись закрытия наряда: подписант — член бригады с ролью из CLOSING_SIGNER_ROLES.

    Вид «сдал/принял» НЕ хранится в запросе — резолвится из роли члена при чтении
    (см. service.signed_closing_kinds).
    """
    role = await _member_role(
        session,
        tenant_id=tenant_id,
        work_permit_id=work_permit_id,
        person_id=person_id,
        allowed_roles=CLOSING_SIGNER_ROLES,
    )
    if role is None:
        raise WorkPermitSignerError("person is not a closing-signer member of this permit")
    return await _dispatch(
        session,
        tenant_id=tenant_id,
        object_type="work_permit_closing",
        object_id=work_permit_id,
        purpose="work_permit_closing",
        person_id=person_id,
        mode=mode,
        requested_by=requested_by,
    )
