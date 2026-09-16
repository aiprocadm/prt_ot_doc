"""BIZ-49 (разд. 49.3): завести и погасить личность специалиста в контуре клиента.

Решение о ПРАВЕ входить принимает ``domains/managed_clients/delegation`` (три
условия: режим Dedicated, контур — потомок аутсорсера, действующее согласие),
как называется и что может личность — ``domains/managed_clients/delegated_identity``.
Здесь только исполнение: сходить в контур клиента и создать либо погасить там
строку пользователя.

## Решения

**1. Отдельная сессия к контуру клиента, а не обход изоляции.** Та же схема и
те же политики строк, что у обычного запроса сотрудника клиента — ровно как в
``services/delegated_attention``. «Системного» режима с отключёнными правилами
здесь нет: он снял бы границу не только там, где нужно.

**2. Личность ОДНА на специалиста и контур.** Повторный вход не плодит учётки:
адрес вычисляется, найденная личность оживляется и обновляется. Иначе за год
работы в контуре клиента накопились бы сотни мёртвых учёток аутсорсера, и
клиент перестал бы понимать свой же список пользователей.

**3. Гашение — это ``is_active = false``, а не удаление.** Удаление оборвало бы
след: строки аудита ссылаются на пользователя, и после удаления стало бы
непонятно, кто именно работал. Погашенная личность мгновенно перестаёт
пускать, потому что проверка прав перечитывает пользователя на каждом запросе.

**4. Ошибку гашения НЕ глушим.** Не сумели погасить — значит дверь в контур
клиента осталась открытой; молчаливое «ну ладно» тут хуже отказа.
"""

from __future__ import annotations

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.domains.managed_clients.delegated_identity import (
    DELEGATED_PASSWORD_MARK,
    delegated_display_name,
    delegated_email,
    delegated_role,
    is_delegated_email,
)
from app.models.identity import User

__all__ = ["ensure_contour_identity", "extinguish_contour_identity"]


async def ensure_contour_identity(
    *,
    client_tenant_slug: str,
    client_tenant_id: str,
    specialist_user_id: str,
    specialist_name: str,
    specialist_role: str | None,
    outsourcer_slug: str,
    outsourcer_name: str,
) -> tuple[str, str]:
    """Завести (или оживить) личность специалиста в контуре клиента.

    Возвращает ``(id личности, её роль)`` — то и другое нужно, чтобы выписать
    токен именно к контуру клиента.
    """

    email = delegated_email(specialist_user_id=specialist_user_id, outsourcer_slug=outsourcer_slug)
    role = delegated_role(specialist_role)
    full_name = delegated_display_name(
        specialist_name=specialist_name, outsourcer_name=outsourcer_name
    )

    async with AsyncSessionLocal(
        tenant=client_tenant_slug, tenant_id=client_tenant_id, create_schema=False
    ) as session:
        row = (
            await session.execute(
                select(User).where(User.tenant_id == client_tenant_id, User.email == email)
            )
        ).scalar_one_or_none()
        if row is None:
            row = User(
                tenant_id=client_tenant_id,
                email=email,
                full_name=full_name,
                role=role,
                hashed_password=DELEGATED_PASSWORD_MARK,
                is_active=True,
            )
            session.add(row)
        else:
            # Роль и имя могли измениться у аутсорсера; личность — отражение
            # гранта, а не самостоятельная запись, поэтому её приводим к нему.
            row.full_name = full_name
            row.role = role
            row.is_active = True
            row.deleted_at = None
        await session.flush()
        identity_id = str(row.id)
        await session.commit()
    return identity_id, role.value


async def extinguish_contour_identity(
    *,
    client_tenant_slug: str,
    client_tenant_id: str,
    specialist_user_id: str,
    outsourcer_slug: str,
) -> bool:
    """Погасить личность специалиста в контуре клиента. ``True`` — гасили.

    Идемпотентно: гасить погашенное или несуществующее — не ошибка, но и не
    повод сказать «погасили», когда гасить было нечего.
    """

    email = delegated_email(specialist_user_id=specialist_user_id, outsourcer_slug=outsourcer_slug)
    async with AsyncSessionLocal(
        tenant=client_tenant_slug, tenant_id=client_tenant_id, create_schema=False
    ) as session:
        row = (
            await session.execute(
                select(User).where(User.tenant_id == client_tenant_id, User.email == email)
            )
        ).scalar_one_or_none()
        if row is None or not is_delegated_email(row.email) or not row.is_active:
            return False
        row.is_active = False
        await session.flush()
        await session.commit()
    return True
