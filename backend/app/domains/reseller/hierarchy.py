"""Иерархия арендаторов: Platform Owner → Reseller → Client (Доп. №1 разд. 52.1).

Правила здесь ЧИСТЫЕ — не ходят в базу, не знают про HTTP и про FastAPI. Причина
не в эстетике: те же правила нужны трём разным местам (создание арендатора
владельцем платформы, создание клиента реселлером, перевод Managed Client в
собственный контур из BIZ-49). Разъедься они по трём местам — иерархия начнёт
означать разное в зависимости от двери, через которую вошли.

Три уровня из ТЗ и как они узнаются:

* ``PLATFORM`` — управляющий арендатор (его slug задан настройкой
  ``PLATFORM_TENANT_SLUG``/``ADMIN_TENANT``). Он один.
* ``RESELLER`` — арендатор с видом ``reseller``. Ведёт СВОИХ клиентов.
* ``CLIENT`` — все остальные (``customer``/``branch``/``contractor``).

Форма дерева выбрана так, чтобы СТАРЫЕ строки остались законными без бэкфилла
(разд. 3 «Non-Destructive Upgrade Principle» плана): корень дерева — владелец
платформы, и его прямые дети хранят ``parent_id = NULL``, как хранили всегда.
Реселлер — тоже прямой ребёнок платформы, поэтому у него ``parent_id = NULL``.
Заполненный ``parent_id`` означает ровно одно: «этот арендатор принадлежит
реселлеру с таким id».
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

#: Значение ``Tenant.kind`` для арендатора-реселлера.
RESELLER_KIND = "reseller"


class TenantLevel(str, Enum):
    """Уровень арендатора в иерархии продажи платформы."""

    PLATFORM = "platform"
    RESELLER = "reseller"
    CLIENT = "client"


@dataclass(frozen=True)
class TenantNode:
    """Минимум сведений об арендаторе, который нужен правилам иерархии.

    Отдельный тип вместо ORM-модели: правила обязаны проверяться на примерах без
    базы, а ORM-объект тянет за собой сессию и схему.
    """

    id: str
    slug: str
    kind: str | None = None
    parent_id: str | None = None
    is_active: bool = True


class HierarchyViolation(ValueError):
    """Нарушение правила иерархии.

    ``code`` уходит в ответ API машиночитаемой строкой: клиент API должен
    отличать «тебе вообще нельзя» от «нельзя именно такого родителя».
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CreationPlan:
    """Что именно записать в новую строку арендатора после проверки правил."""

    kind: str
    parent_id: str | None


def resolve_level(node: TenantNode, *, managing_slug: str) -> TenantLevel:
    """Определить уровень арендатора.

    Проверка на платформу идёт ПЕРВОЙ: если управляющему арендатору когда-нибудь
    проставят вид ``reseller``, он всё равно обязан остаться владельцем
    платформы, иначе одна правка строки в базе понижает владельца в партнёры.
    """

    if node.slug.strip().lower() == managing_slug.strip().lower():
        return TenantLevel.PLATFORM
    if (node.kind or "").strip().lower() == RESELLER_KIND:
        return TenantLevel.RESELLER
    return TenantLevel.CLIENT


def plan_tenant_creation(
    *,
    actor: TenantNode,
    requested_kind: str,
    requested_parent_id: str | None,
    parent: TenantNode | None,
    managing_slug: str,
) -> CreationPlan:
    """Проверить право на создание арендатора и вернуть, что записать.

    ``actor`` — арендатор, от имени которого пришёл запрос. ``parent`` — уже
    загруженная строка родителя, если ``requested_parent_id`` задан; ``None``
    означает «родитель не запрошен», а не «родитель не найден»: ненайденного
    родителя обязан отсеять вызывающий, иначе молчаливое ``None`` превратило бы
    опечатку в id в «создать под платформой».
    """

    kind = (requested_kind or "").strip().lower()
    level = resolve_level(actor, managing_slug=managing_slug)

    if level is TenantLevel.CLIENT:
        raise HierarchyViolation(
            "TENANT_CREATION_FORBIDDEN",
            "Создавать арендаторов может владелец платформы или реселлер",
        )

    if level is TenantLevel.RESELLER:
        if not actor.is_active:
            raise HierarchyViolation(
                "RESELLER_SUSPENDED",
                "Приостановленный реселлер не может заводить клиентов",
            )
        if kind == RESELLER_KIND:
            raise HierarchyViolation(
                "RESELLER_CANNOT_CREATE_RESELLER",
                "Реселлер не может создать другого реселлера: уровней всего три",
            )
        # Реселлеру нельзя подвесить клиента к чужому родителю. Запрошенный
        # родитель либо не указан, либо обязан совпасть с ним самим — иначе
        # партнёр заводил бы клиентов в контуре соседа.
        if requested_parent_id is not None and requested_parent_id != actor.id:
            raise HierarchyViolation(
                "RESELLER_PARENT_MISMATCH",
                "Реселлер заводит клиентов только в своём контуре",
            )
        return CreationPlan(kind=kind or "customer", parent_id=actor.id)

    # Владелец платформы.
    if kind == RESELLER_KIND:
        if requested_parent_id is not None:
            raise HierarchyViolation(
                "RESELLER_MUST_BE_ROOT",
                "Реселлер подчиняется владельцу платформы напрямую, без родителя",
            )
        return CreationPlan(kind=RESELLER_KIND, parent_id=None)

    if requested_parent_id is None:
        return CreationPlan(kind=kind or "customer", parent_id=None)

    if parent is None:
        raise HierarchyViolation("TENANT_PARENT_NOT_FOUND", "Родитель не найден")
    validate_parent_candidate(parent, managing_slug=managing_slug)
    return CreationPlan(kind=kind or "customer", parent_id=parent.id)


def validate_parent_candidate(parent: TenantNode, *, managing_slug: str) -> None:
    """Проверить, годится ли арендатор в родители.

    Родителем может быть ТОЛЬКО реселлер. Платформа родителем не бывает по форме
    дерева (её дети хранят ``NULL``), а клиент — потому что четвёртого уровня в
    ТЗ нет: разреши его, и «реселлер не видит чужих клиентов» перестанет быть
    проверяемым свойством — глубина станет произвольной.
    """

    level = resolve_level(parent, managing_slug=managing_slug)
    if level is TenantLevel.PLATFORM:
        raise HierarchyViolation(
            "TENANT_PARENT_IS_PLATFORM",
            "Клиенты платформы хранятся без родителя",
        )
    if level is TenantLevel.CLIENT:
        raise HierarchyViolation(
            "TENANT_PARENT_NOT_RESELLER",
            "Родителем арендатора может быть только реселлер",
        )
    if not parent.is_active:
        raise HierarchyViolation(
            "RESELLER_SUSPENDED",
            "Приостановленный реселлер не может принимать новых клиентов",
        )


def inherited_parent_for_spawned_tenant(owner: TenantNode, *, managing_slug: str) -> str | None:
    """Кому принадлежит арендатор, который контур завёл сам себе.

    Случай из BIZ-49: клиента переводят в режим Dedicated, и приложение создаёт
    ему собственного арендатора. Владелец нового арендатора — тот контур, где
    нажали кнопку. Если это реселлер, новый арендатор обязан лечь ПОД него;
    иначе клиент партнёра оказался бы корневым — то есть на одном уровне с самим
    партнёром и вне его кабинета.
    """

    level = resolve_level(owner, managing_slug=managing_slug)
    if level is TenantLevel.RESELLER:
        return owner.id
    if level is TenantLevel.CLIENT:
        # Клиент реселлера, переводящий СВОЕГО подопечного, остаётся в контуре
        # того же реселлера: дед не меняется, четвёртого уровня не появляется.
        return owner.parent_id
    return None
