"""Область видимости флота: кто каких арендаторов видит (Доп. №1 разд. 52.1, 52.4).

Срез-1 научил систему различать уровни. Этот модуль отвечает на следующий
вопрос: какое подмножество арендаторов принадлежит тому, кто пришёл.

Правила снова ЧИСТЫЕ и без базы — их проверяют на примерах, а SQL-условие
строится из результата. Причина та же, что у `hierarchy.py`: одна и та же
область нужна списку, пяти ручкам правки и выдаче нового арендатора. Посчитай её
в шести местах — и «свой клиент» начнёт означать разное в зависимости от ручки.

Форма дерева (из среза-1): прямые клиенты платформы держат ``parent_id = NULL``,
клиенты партнёра — ``parent_id = <id партнёра>``. Поэтому «поддерево партнёра»
выражается одним равенством, без рекурсии: четвёртого уровня в ТЗ нет.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.reseller.hierarchy import (
    HierarchyViolation,
    TenantLevel,
    TenantNode,
    resolve_level,
)


@dataclass(frozen=True)
class FleetScope:
    """Что видит и чем управляет пришедший.

    ``owner_id`` — id партнёра, чьё поддерево показываем; ``None`` означает «весь
    флот» и бывает только у владельца платформы.
    """

    level: TenantLevel
    owner_id: str | None

    @property
    def sees_everything(self) -> bool:
        return self.level is TenantLevel.PLATFORM

    @property
    def may_change_commercials(self) -> bool:
        """Можно ли менять тариф, квоты и пробный доступ.

        Пока только владельцу платформы. У партнёра нет потолка «нельзя выдать
        клиенту больше, чем есть у тебя» — без него партнёр раздавал бы
        «Всё включено» бесплатно за счёт владельца. Потолок появится вместе с
        суб-биллингом (разд. 52.4), тогда это правило и смягчится.
        """

        return self.level is TenantLevel.PLATFORM


def resolve_fleet_scope(actor: TenantNode, *, managing_slug: str) -> FleetScope:
    """Определить область флота для пришедшего или отказать.

    Отказ — единственный для клиентского уровня: у обычного арендатора кабинета
    флота нет вовсе.
    """

    level = resolve_level(actor, managing_slug=managing_slug)
    if level is TenantLevel.PLATFORM:
        return FleetScope(level=level, owner_id=None)
    if level is TenantLevel.RESELLER:
        if not actor.is_active:
            raise HierarchyViolation(
                "RESELLER_SUSPENDED",
                "Кабинет приостановленного партнёра закрыт",
            )
        return FleetScope(level=level, owner_id=actor.id)
    raise HierarchyViolation(
        "FLEET_ACCESS_FORBIDDEN",
        "Кабинет арендаторов доступен владельцу платформы и партнёрам",
    )


def is_in_scope(scope: FleetScope, target: TenantNode) -> bool:
    """Принадлежит ли арендатор области.

    Партнёру принадлежат ТОЛЬКО его клиенты — сам он себе не принадлежит
    (`parent_id` партнёра пуст). Это не придирка: иначе партнёр смог бы
    приостановить сам себя и запереть собственный кабинет.
    """

    if scope.sees_everything:
        return True
    return target.parent_id is not None and target.parent_id == scope.owner_id
