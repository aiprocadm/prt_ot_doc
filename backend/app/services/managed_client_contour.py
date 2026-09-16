"""BIZ-49 (разд. 49.3): вход специалиста В КОНТУР Dedicated-клиента.

Срез-126 научил платформу ЧИТАТЬ контур клиента для сводки портфеля и честно
записал остаток: интерактивной работы человека внутри контура (вход, запись)
не было. Причина названа там же точно: **строки ``User`` живут в схеме
арендатора**, а значит у специалиста аутсорсера в контуре клиента нет личности,
и боевая проверка прав его туда не пустит.

Здесь — сборка входа из трёх готовых частей:

1. **право** — ``domains/managed_clients/delegation`` (режим Dedicated, контур
   заведён ПОД этим аутсорсером, есть действующее согласие);
2. **личность** — ``services/managed_client_identity`` (завести или оживить в
   контуре клиента);
3. **ключ** — токен доступа К КОНТУРУ КЛИЕНТА на эту личность.

## Решения

**1. Вход в контур — не отдельная дверь, а продолжение входа в контекст.**
Тот же роут, тот же журнал, тот же срок, тот же отзыв. Вторая дверь означала
бы второй набор проверок, и однажды они разошлись бы.

**2. У токена контура НЕТ обновления (refresh).** Обновление пережило бы и срок
контекста, и отзыв согласия: специалист остался бы в контуре клиента навсегда,
ни разу больше не предъявив основания. Продлить работу можно только входом в
контекст заново — а он перепроверяет всё.

**3. Токен НЕСЁТ метку делегирования.** Заголовок можно не прислать, а метку в
подписанном токене — нет. По ней сторож запретов (разд. 63.2) узнаёт работу «от
имени» и в чужом контуре, где заголовка нет вовсе.

**4. Отказ называет причину словами.** «Контур недоступен» без объяснения
читается как поломка платформы; человеку надо понять, идти ли за согласием,
поднимать контур или связывать иерархию.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import issue_access_token
from app.domains.managed_clients.consent import ClientConsent
from app.domains.managed_clients.delegated_identity import (
    DELEGATED_CLIENT_CLAIM,
    DELEGATED_FROM_CLAIM,
    delegated_display_name,
)
from app.domains.managed_clients.delegation import evaluate_delegated_read
from app.models.identity import User
from app.models.managed_clients import ManagedClient, ManagedClientConsent
from app.models.tenanting import Tenant
from app.services.managed_client_identity import (
    ensure_contour_identity,
    extinguish_contour_identity,
)

__all__ = ["ContourEntry", "close_contour_session", "open_contour_session"]

#: Контур не выдаётся, и это нормально: у Lightweight-клиента его нет.
NO_CONTOUR_NEEDED = ""


@dataclass(frozen=True)
class ContourEntry:
    """Ключ от контура клиента и то, как специалист там подписан."""

    tenant_slug: str
    access_token: str
    role: str
    display_name: str


async def _client_consents(
    session: AsyncSession, *, outsourcer_tenant_id: str, client_id: str
) -> list[ClientConsent]:
    rows = (
        (
            await session.execute(
                select(ManagedClientConsent).where(
                    ManagedClientConsent.tenant_id == outsourcer_tenant_id,
                    ManagedClientConsent.managed_client_id == client_id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [
        ClientConsent(
            client_id=str(row.managed_client_id),
            document_ref=row.document_ref,
            granted_at=row.granted_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )
        for row in rows
    ]


async def open_contour_session(
    session: AsyncSession,
    *,
    client: ManagedClient,
    outsourcer_tenant: Tenant,
    specialist_user_id: str,
    now: datetime,
) -> tuple[ContourEntry | None, str]:
    """Пустить специалиста в контур клиента. ``(None, причина)`` — не пустили.

    Причина возвращается словами и предназначена человеку: она попадает в
    ответ ручки входа в контекст.
    """

    slug = (client.dedicated_tenant_slug or "").strip()
    client_tenant = None
    if slug:
        client_tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()

    verdict = evaluate_delegated_read(
        mode=client.mode,
        client_tenant_slug=slug or None,
        client_tenant_exists=client_tenant is not None,
        client_tenant_parent_id=getattr(client_tenant, "parent_id", None),
        client_tenant_is_active=bool(getattr(client_tenant, "is_active", False)),
        outsourcer_tenant_id=str(outsourcer_tenant.id),
        consents=await _client_consents(
            session, outsourcer_tenant_id=str(outsourcer_tenant.id), client_id=client.id
        ),
        now=now,
    )
    if not verdict.allowed or client_tenant is None:
        return None, verdict.reason or "Контур клиента недоступен"

    specialist = (
        await session.execute(
            select(User).where(
                User.tenant_id == outsourcer_tenant.id, User.id == specialist_user_id
            )
        )
    ).scalar_one_or_none()
    if specialist is None:
        # Такого быть не должно: запрос уже прошёл проверку прав. Но молча
        # выдать ключ «неизвестно кому» нельзя — в контуре клиента личность
        # обязана быть подписана именем.
        return None, "Специалист не найден в контуре аутсорсера"

    outsourcer_name = str(getattr(outsourcer_tenant, "name", "") or outsourcer_tenant.slug)
    identity_id, role_value = await ensure_contour_identity(
        client_tenant_slug=str(client_tenant.slug),
        client_tenant_id=str(client_tenant.id),
        specialist_user_id=str(specialist.id),
        specialist_name=str(specialist.full_name or ""),
        specialist_role=specialist.role.value if specialist.role else None,
        outsourcer_slug=str(outsourcer_tenant.slug),
        outsourcer_name=outsourcer_name,
    )

    token = issue_access_token(
        subject=identity_id,
        tenant=str(client_tenant.slug),
        role=role_value,
        additional_claims={
            "tenant_id": str(client_tenant.id),
            "roles": [role_value],
            # Метка делегирования: по ней запреты разд. 63.2 действуют и здесь.
            DELEGATED_CLIENT_CLAIM: str(client.id),
            DELEGATED_FROM_CLAIM: str(outsourcer_tenant.slug),
        },
    )
    return (
        ContourEntry(
            tenant_slug=str(client_tenant.slug),
            access_token=token,
            role=role_value,
            display_name=delegated_display_name(
                specialist_name=str(specialist.full_name or ""),
                outsourcer_name=outsourcer_name,
            ),
        ),
        NO_CONTOUR_NEEDED,
    )


async def close_contour_session(
    session: AsyncSession,
    *,
    client: ManagedClient,
    outsourcer_slug: str,
    specialist_user_id: str,
) -> bool:
    """Погасить личность специалиста в контуре клиента. ``True`` — гасили.

    Вызывается при выходе из контекста и при отзыве основания. Гашение
    действует немедленно: проверка прав перечитывает пользователя на каждом
    запросе, поэтому доживающий токен уже никуда не пускает.
    """

    slug = (client.dedicated_tenant_slug or "").strip()
    if not slug:
        return False
    client_tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == slug))
    ).scalar_one_or_none()
    if client_tenant is None:
        return False
    return await extinguish_contour_identity(
        client_tenant_slug=str(client_tenant.slug),
        client_tenant_id=str(client_tenant.id),
        specialist_user_id=str(specialist_user_id),
        outsourcer_slug=str(outsourcer_slug),
    )
