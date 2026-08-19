"""Связь «пользователь → сотрудник» (Person) в одном месте.

Прямой связи у моделей нет: у ``User`` нет ``person_id``. Исторически проект
сопоставляет их по e-mail без учёта регистра — так делает карточка сотрудника
и офлайн-выгрузка PWA. Приём переехал сюда, когда третьим потребителем стал
Центр внимания (BIZ-54-57 срез-1): третья копия одного SQL разошлась бы с
первыми двумя, а цена расхождения здесь — чужие персональные данные на экране.

**Отсутствие связи — законный исход, а не ошибка.** У администратора без
кадровой записи персональных сроков нет; вызывающий обязан показать пустоту,
а НЕ откатиться на список всего арендатора — это и была бы утечка.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Person

__all__ = ["resolve_person_id"]


async def resolve_person_id(
    session: AsyncSession, tenant_id: Any, user_email: Any
) -> str | None:
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
