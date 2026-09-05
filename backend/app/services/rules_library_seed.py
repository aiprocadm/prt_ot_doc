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

Посев идемпотентен по ИМЕНИ правила: повторная выдача не плодит копий.

**Удалённое специалистом правило НЕ возвращается** (срез-63). Удаление у правил
мягкое (``deleted_at``), а имя уникально на арендатора БЕЗ учёта удалённых
(``uq_automation_rule_tenant_name``) — значит, повторный посев по «живым»
именам упёрся бы в ограничение базы на первом же удалённом правиле. Поэтому
посев смотрит на ВСЕ имена, включая удалённые: удалённое — решение
специалиста, и оно называется в итоге отдельно (``kept_deleted``), а не
пересоздаётся молча. Вернуть такое правило можно только руками, новым именем.

До среза-63 посев вызывался лишь при создании арендатора; с среза-63 его можно
вызвать ещё и ручкой ``POST /rules/library/install`` — так существующие
арендаторы получают правила, добавленные в библиотеку позже (срез-62 дал
шесть правил по срокам дисциплин, и без ручки они появились бы только у новых
арендаторов).
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.rules_library.library import LIBRARY_RULES, coverage
from app.models.rules_engine import AutomationRule

__all__ = [
    "RuleLibraryInstallOutcome",
    "install_rule_library",
    "library_coverage",
    "library_rule_names",
    "library_size",
    "library_state",
    "seed_rule_library",
]


# Посредники для модуля правил: страж границ ARCH-3 запрещает
# ``app.modules.* → app.domains.*``, а ``modules → services`` разрешён (тот же
# приём, что у сигналов ленты изменений в BIZ-51 срезе-2). Копии данных здесь
# нет — только проброс, иначе библиотека разошлась бы сама с собой.
def library_coverage(*, alive: Collection[str] = (), deleted: Collection[str] = ()) -> list[dict]:
    """Покрытие дисциплин библиотекой: числа, причины отсутствия и имена
    не выданных / удалённых у арендатора правил (срез-66)."""

    return coverage(alive=alive, deleted=deleted)


def library_rule_names() -> list[str]:
    """Имена правил библиотеки — по ним считается, сколько уже выдано."""

    return [rule.name for rule in LIBRARY_RULES]


def library_size() -> int:
    """Сколько правил в библиотеке продукта."""

    return len(LIBRARY_RULES)


@dataclass(frozen=True)
class RuleLibraryInstallOutcome:
    """Итог выдачи библиотеки арендатору — честный, по именам.

    ``created`` — что завели сейчас; ``kept_deleted`` — что в библиотеке есть,
    но специалист удалил, и мы НЕ вернули; ``installed`` — сколько правил
    библиотеки живёт у арендатора после выдачи; ``total`` — размер библиотеки.
    """

    created: tuple[str, ...] = ()
    kept_deleted: tuple[str, ...] = ()
    installed: int = 0
    total: int = 0


async def library_state(session: AsyncSession, *, tenant_id: str) -> tuple[set[str], set[str]]:
    """Имена правил библиотеки у арендатора: (живые, удалённые специалистом)."""

    names = library_rule_names()
    rows = (
        await session.execute(
            select(AutomationRule.name, AutomationRule.deleted_at).where(
                AutomationRule.tenant_id == tenant_id,
                AutomationRule.name.in_(names),
            )
        )
    ).all()
    alive = {str(name) for name, deleted_at in rows if deleted_at is None}
    deleted = {str(name) for name, deleted_at in rows if deleted_at is not None}
    return alive, deleted


async def install_rule_library(
    session: AsyncSession, *, tenant_id: str
) -> RuleLibraryInstallOutcome:
    """Завести недостающие правила библиотеки, не трогая удалённые.

    Ничего не коммитит — транзакцией владеет вызывающий.
    """

    alive, deleted = await library_state(session, tenant_id=tenant_id)

    created: list[str] = []
    kept_deleted: list[str] = []
    for rule in LIBRARY_RULES:
        if rule.name in alive:
            continue
        if rule.name in deleted:
            kept_deleted.append(rule.name)
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
        created.append(rule.name)
    if created:
        await session.flush()
    return RuleLibraryInstallOutcome(
        created=tuple(created),
        kept_deleted=tuple(kept_deleted),
        installed=len(alive) + len(created),
        total=library_size(),
    )


async def seed_rule_library(session: AsyncSession, *, tenant_id: str) -> int:
    """Завести недостающие правила библиотеки. Возвращает число созданных.

    Тонкая обёртка над :func:`install_rule_library` для посева при создании
    арендатора. Ничего не коммитит — транзакцией владеет вызывающий.
    """

    outcome = await install_rule_library(session, tenant_id=tenant_id)
    return len(outcome.created)
