"""Связь «пользователь → сотрудник» (Person) в одном месте.

Прямой связи у моделей нет: у ``User`` нет ``person_id``. Исторически проект
сопоставляет их по e-mail без учёта регистра — так делает карточка сотрудника
и офлайн-выгрузка PWA. Приём переехал сюда, когда третьим потребителем стал
Центр внимания (BIZ-54-57 срез-1): третья копия одного SQL разошлась бы с
первыми двумя, а цена расхождения здесь — чужие персональные данные на экране.

**Отсутствие связи — законный исход, а не ошибка.** У администратора без
кадровой записи персональных сроков нет; вызывающий обязан показать пустоту,
а НЕ откатиться на список всего арендатора — это и была бы утечка.

**Обратное направление тоже здесь (срез-119).** «Кто из пользователей — это
вот этот работник?» спрашивают карточка сотрудника (показать учётную запись)
и движок правил (написать самому работнику, срез-118). Правило сопоставления
у них ОДНО, и разъехаться ему нельзя: ошибка в одну сторону покажет чужую
учётную запись, в другую — отправит человеку чужое уведомление. Поэтому
``resolve_user`` живёт рядом с ``resolve_person_id``, а не переписывается
в каждом вызывающем.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User
from app.models.master_data import Person

__all__ = ["resolve_person_id", "resolve_user", "resolve_user_id"]


async def resolve_person_id(session: AsyncSession, tenant_id: Any, user_email: Any) -> str | None:
    """Найти сотрудника, соответствующего пользователю, или вернуть ``None``."""

    if not user_email:
        return None
    return (
        await session.execute(
            select(Person.id)
            .where(
                Person.tenant_id == tenant_id,
                func.lower(Person.email) == str(user_email).lower(),
                Person.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_user(session: AsyncSession, tenant_id: Any, person_email: Any) -> User | None:
    """Найти учётную запись, соответствующую работнику, или вернуть ``None``.

    Обратная сторона ``resolve_person_id``: то же сопоставление по e-mail без
    учёта регистра, в ту же сторону арендатора. Удалённые пользователи не
    считаются; ``is_active`` НЕ проверяется — «выключен» решает вызывающий,
    как и в остальных местах продукта.
    """

    if not person_email:
        return None
    return (
        await session.execute(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                func.lower(User.email) == str(person_email).lower(),
                User.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def resolve_user_id(session: AsyncSession, tenant_id: Any, person_email: Any) -> str | None:
    """``resolve_user``, когда нужен только идентификатор."""

    user = await resolve_user(session, tenant_id, person_email)
    return str(user.id) if user is not None else None
