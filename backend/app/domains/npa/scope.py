"""Видимость нормативного акта: общий реестр плюс акты САМОГО арендатора.

Срез-201 (B.18 разд. 19.1). Реестр ``npa_act`` знал только федеральные акты,
заведённые владельцем платформы. Свой приказ по организации («О назначении
ответственного за электрохозяйство») арендатор записать не мог вовсе — а
значит, не мог ни привязать к нему документ, ни завести по нему требование, ни
увидеть его в оценке влияния. Вся обвязка существовала, и была недоступна ровно
для тех актов, которые арендатор пишет сам.

**Почему фильтр живёт здесь, а не рассыпан по запросам.** ``npa_act`` — общая
таблица (``SharedModel``), она вне схемы арендатора и вне RLS: база НЕ подстрахует.
Единственный рубеж — условие в запросе, и пропустить его можно ровно один раз,
чтобы один арендатор увидел приказы другого. Поэтому спрашивать акты
разрешено ТОЛЬКО через этот модуль, а прямые ``select(NpaAct)`` и
``session.get(NpaAct, ...)`` в остальном коде запрещены сторожем
``tests/test_npa_scope_guard.py``.

Правило видимости одно, и оно сложением, а не выбором:

* ``owner_tenant_id IS NULL`` — общий реестр платформы, виден всем арендаторам;
* ``owner_tenant_id = <мой>`` — мои собственные акты.

Чужой локальный акт не виден НИКОМУ, включая владельца платформы: он
нормативка арендатора, а не платформы.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.npa import NpaAct

__all__ = [
    "REGISTRY_SCOPE",
    "SCOPE_TITLES",
    "TENANT_SCOPE",
    "act_scope_clause",
    "find_act_by_code",
    "get_visible_act",
    "registry_first",
    "scope_of",
    "scope_title",
    "visible_acts",
]

#: Куда пишет заводящий акт. Поле явное, а не угадываемое по роли: «завести
#: федеральный акт» и «завести свой приказ» — разные поступки с разной ценой
#: ошибки, и человек должен назвать, какой из них он совершает.
REGISTRY_SCOPE = "registry"
TENANT_SCOPE = "own"

#: Подпись словами приходит С СЕРВЕРА. Витрина не должна знать, что "own"
#: значит «наш приказ»: перевод кода в слово — это и есть то место, где экраны
#: раз за разом печатали служебный код вместо человеческого текста.
SCOPE_TITLES: dict[str, str] = {
    REGISTRY_SCOPE: "Общий реестр",
    TENANT_SCOPE: "Акт организации",
}


def act_scope_clause(tenant_id: str | None) -> ColumnElement[bool]:
    """Условие «этот акт мне видно».

    ``tenant_id is None`` означает «арендатора нет вовсе» (фоновая задача без
    контура). Тогда видно только общий реестр — но НЕ чьи-то локальные акты:
    отсутствие арендатора не должно превращаться в «видно всё».
    """

    if tenant_id is None:
        return NpaAct.owner_tenant_id.is_(None)
    return or_(NpaAct.owner_tenant_id.is_(None), NpaAct.owner_tenant_id == tenant_id)


def visible_acts(tenant_id: str | None) -> Select[tuple[NpaAct]]:
    """``select(NpaAct)``, уже суженный до видимого. Точка входа для списков."""

    return select(NpaAct).where(act_scope_clause(tenant_id))


async def get_visible_act(
    session: AsyncSession, act_id: str, tenant_id: str | None
) -> NpaAct | None:
    """Замена ``session.get(NpaAct, act_id)``.

    ``session.get`` берёт строку по первичному ключу и никаких условий не
    принимает — именно поэтому он здесь запрещён: идентификатор акта приходит
    из тела запроса, и по чужому идентификатору вернулась бы чужая строка.
    «Не видно» отвечается как «нет» (``None``), чтобы по коду ответа нельзя
    было пересчитать чужие акты.
    """

    return await session.scalar(visible_acts(tenant_id).where(NpaAct.id == act_id))


async def find_act_by_code(
    session: AsyncSession, code: str, owner_tenant_id: str | None
) -> str | None:
    """Идентификатор акта с таким кодом У ЭТОГО ЖЕ владельца, или ``None``.

    Проверка занятости кода обязана смотреть в тот же ящик, в который будет
    запись: общий код занят глобально, локальный — только внутри арендатора.
    Иначе «Приказ №1» достался бы первому, кто успел, а остальным вечно
    отвечали бы 409 про акт, которого они не видят.
    """

    owner_clause = (
        NpaAct.owner_tenant_id.is_(None)
        if owner_tenant_id is None
        else NpaAct.owner_tenant_id == owner_tenant_id
    )
    return await session.scalar(select(NpaAct.id).where(owner_clause, NpaAct.code == code))


def registry_first() -> ColumnElement[bool]:
    """Порядок «сначала общий реестр, потом свои акты» для списка.

    Живёт здесь по той же причине, что и фильтр: это второе выражение про
    ``owner_tenant_id``, и разъехаться они не должны. Сторож
    ``tests/test_npa_scope_guard.py`` держит оба в одном файле.
    """

    return NpaAct.owner_tenant_id.is_(None).desc()


def scope_of(act: NpaAct) -> str:
    """Общий реестр или собственный акт арендатора."""

    return REGISTRY_SCOPE if act.owner_tenant_id is None else TENANT_SCOPE


def scope_title(act: NpaAct) -> str:
    """То же словами — для экрана."""

    return SCOPE_TITLES[scope_of(act)]
