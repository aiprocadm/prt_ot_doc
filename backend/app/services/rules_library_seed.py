"""Выдача библиотеки правил арендатору (BIZ-54-57 срез-4, Доп. №1 разд. 57.3).

Правила библиотеки становятся ОБЫЧНЫМИ правилами арендатора: их видно на
экране «Правила», их можно выключить, поправить условие или удалить. Библиотека
— стартовая экспертиза, а не запертый ящик: специалист имеет право не
согласиться с правилом.

**Выдаём ВСЕМ, даже без купленного модуля.** Движок сам проверяет модуль перед
срабатыванием (``engine._evaluate_event``), поэтому у арендатора без модуля
правила лежат и молчат. Это то же различие, что у выдачи модулей в BIZ-53:
«есть и выключено» и «никогда не выдавалось» — разные состояния, и второе
означало бы, что купивший модуль позже получит пустой движок.

Посев идемпотентен по ИМЕНИ правила: повторная выдача не плодит копий. Но
удалённое правило по имени не найдётся и будет заведено снова — поэтому посев
вызывается при создании арендатора, а не на каждом запуске: иначе система
возвращала бы то, что специалист осознанно убрал.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.rules_library.library import LIBRARY_RULES, coverage
from app.models.rules_engine import AutomationRule

__all__ = ["library_coverage", "library_rule_names", "library_size", "seed_rule_library"]


# Посредники для модуля правил: страж границ ARCH-3 запрещает
# ``app.modules.* → app.domains.*``, а ``modules → services`` разрешён (тот же
# приём, что у сигналов ленты изменений в BIZ-51 срезе-2). Копии данных здесь
# нет — только проброс, иначе библиотека разошлась бы сама с собой.
def library_coverage() -> list[dict]:
    """Покрытие дисциплин библиотекой: числа и причины отсутствия."""

    return coverage()


def library_rule_names() -> list[str]:
    """Имена правил библиотеки — по ним считается, сколько уже выдано."""

    return [rule.name for rule in LIBRARY_RULES]


def library_size() -> int:
    """Сколько правил в библиотеке продукта."""

    return len(LIBRARY_RULES)


async def seed_rule_library(session: AsyncSession, *, tenant_id: str) -> int:
    """Завести недостающие правила библиотеки. Возвращает число созданных.

    Ничего не коммитит — транзакцией владеет вызывающий.
    """

    existing = {
        str(name)
        for name in (
            await session.execute(
                select(AutomationRule.name).where(
                    AutomationRule.tenant_id == tenant_id,
                    AutomationRule.deleted_at.is_(None),
                )
            )
        ).scalars()
    }

    created = 0
    for rule in LIBRARY_RULES:
        if rule.name in existing:
            continue
        session.add(
            AutomationRule(
                tenant_id=tenant_id,
                name=rule.name,
                description=rule.description,
                event_type=rule.event_type,
                conditions_json=dict(rule.conditions),
                actions_json=[dict(action) for action in rule.actions],
                priority=rule.priority,
                is_enabled=True,
            )
        )
        created += 1
    if created:
        await session.flush()
    return created
