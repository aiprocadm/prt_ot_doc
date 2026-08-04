"""BIZ-49 срез-6 (разд. 49.3): матрица доступа «специалист аутсорсера → клиент».

Чистые правила без БД. Это контроль доступа, поэтому решения об УМОЛЧАНИЯХ
важнее всего остального — именно неясность в них и есть та дыра, через которую
доступ утекает:

* **умолчание — запрет.** Нет гранта — нет клиента; модуль не перечислен —
  доступа к модулю нет. «Пустой список = всё» выглядит удобно ровно до первой
  забытой строки, после которой специалист видит чужого клиента целиком;
* **«весь клиент» объявляется явно** (``all_modules``), а не выводится из
  пустоты. Противоречивый грант (и «весь клиент», и список модулей) отвергается:
  какое из двух намерений было настоящим, потом уже не докажешь;
* **отзыв — момент времени, а не удаление строки.** ТЗ требует, чтобы действия
  аутсорсера в данных клиента были трассируемы; удалив грант, мы потеряем
  ответ на вопрос «а имел ли он доступ, когда это сделал».
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

__all__ = [
    "AccessGrant",
    "AccessGrantError",
    "grant_allows",
    "is_grant_active",
    "validate_grant",
    "visible_client_ids",
]


class AccessGrantError(ValueError):
    """Грант противоречив или пуст."""


@dataclass(frozen=True)
class AccessGrant:
    client_id: str
    user_id: str
    all_modules: bool
    modules: tuple[str, ...]
    revoked_at: datetime | None = None


def validate_grant(*, all_modules: bool, modules: tuple[str, ...] | list[str]) -> None:
    """Проверить намерение гранта до записи."""

    mods = tuple(modules)
    if all_modules and mods:
        raise AccessGrantError(
            "Грант «весь клиент» не может одновременно ограничивать список модулей"
        )
    if not all_modules and not mods:
        raise AccessGrantError(
            "Грант должен указывать модули либо явно давать доступ ко всему клиенту"
        )
    if len(set(mods)) != len(mods):
        raise AccessGrantError("Список модулей содержит повторы")


def _as_utc(value: datetime) -> datetime:
    """Нормализовать момент к UTC.

    Из базы дата может прийти БЕЗ часового пояса (так ведёт себя SQLite и часть
    драйверов), а сравнение naive с aware падает с TypeError. Проверка доступа
    не имеет права ронять запрос из-за формата хранения времени.
    """

    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_grant_active(grant: AccessGrant, *, now: datetime) -> bool:
    """Действует ли грант НА МОМЕНТ ``now`` (нужно и для разбора прошлого)."""

    if grant.revoked_at is None:
        return True
    return _as_utc(grant.revoked_at) > _as_utc(now)


def grant_allows(grant: AccessGrant, *, module: str | None, now: datetime) -> bool:
    """Пускает ли грант к клиенту (``module=None``) или к его модулю."""

    if not is_grant_active(grant, now=now):
        return False
    if module is None or grant.all_modules:
        return True
    return module in grant.modules


def visible_client_ids(
    grants: list[AccessGrant] | tuple[AccessGrant, ...], *, user_id: str, now: datetime
) -> set[str]:
    """Клиенты, доступные специалисту сейчас, — основа переключателя клиентов."""

    return {g.client_id for g in grants if g.user_id == user_id and is_grant_active(g, now=now)}
