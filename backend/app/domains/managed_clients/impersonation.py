"""BIZ-49 срез-10 (Доп. №3, разд. 63.2): границы работы «от имени клиента».

Срезы 7–9 сделали работу «от имени» рабочей: подтверждение гранта, след в аудите,
фильтр данных. ТЗ называет её «мощно и опасно» и требует двух ограничений,
которых до сих пор не было:

* **срок.** «Сессия имперсонации истекает (напр. 60 мин), не навсегда».
  Контекст переживает перезагрузку страницы (срез-8), то есть без срока он
  живёт буквально вечно: специалист ушёл домой, а платформа считает, что он
  всё ещё работает от имени клиента;
* **список запретов.** «Что имперсонатору ЗАПРЕЩЕНО даже в контексте клиента:
  менять пароли/2FA клиента, платёжные данные, массовый экспорт ПДн, удаление
  данных, изменение настроек безопасности».

Здесь чистые правила без БД и без FastAPI.

Три решения, которые важнее кода:

* **Запреты объявлены списком путей, а не разбросаны по роутам.** Проверка,
  расставленная руками по обработчикам, забывается ровно на том роуте, где
  она нужнее всего, и никто этого не замечает — отказа-то нет.
* **Выход из контекста запрещать нельзя.** Иначе запрет запирает сам себя:
  специалист не может ни удалить (запрещено), ни выйти (тоже запрещено).
* **Отказ всегда объясняет причину и что делать.** «Запрещено» без причины
  читается как поломка платформы и уходит в поддержку.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

__all__ = [
    "CONTEXT_TTL",
    "FORBIDDEN_IN_CONTEXT",
    "ForbiddenInContext",
    "ForbiddenRule",
    "ImpersonationExpired",
    "ensure_action_allowed",
    "ensure_session_active",
    "session_expires_at",
    "session_seconds_left",
]

#: Срок жизни работы «от имени клиента». 60 минут прямо названы в ТЗ как
#: пример; берём их, потому что это рабочая сессия, а не смена.
CONTEXT_TTL = timedelta(minutes=60)


class ImpersonationExpired(PermissionError):
    """Контекст клиента истёк или был закрыт."""


class ForbiddenInContext(PermissionError):
    """Действие запрещено в контексте клиента (Доп. №3, разд. 63.2)."""


@dataclass(frozen=True)
class ForbiddenRule:
    """Запрет: методы + начала путей + причина человеческим языком."""

    prefixes: tuple[str, ...]
    reason: str
    #: Пустой набор = «любым методом».
    methods: frozenset[str] = frozenset()

    def matches(self, *, method: str, path: str) -> bool:
        if self.methods and method.upper() not in self.methods:
            return False
        return path.startswith(self.prefixes)


_V1 = "/api/v1"

#: Пути, которые обязаны работать и в контексте, что бы ни говорили запреты
#: ниже. Выход из контекста — первый из них: запрет, запирающий сам себя,
#: оставляет специалиста работать «от имени» без возможности это прекратить.
_ALWAYS_ALLOWED: tuple[str, ...] = (
    f"{_V1}/managed-clients/context",
    f"{_V1}/auth/login",
    f"{_V1}/auth/logout",
    f"{_V1}/auth/refresh",
)

FORBIDDEN_IN_CONTEXT: tuple[ForbiddenRule, ...] = (
    ForbiddenRule(
        prefixes=(f"{_V1}/auth/", f"{_V1}/users/"),
        reason=(
            "смена пароля и двухфакторной защиты — это захват учётной записи, "
            "а не работа с данными клиента"
        ),
    ),
    ForbiddenRule(
        prefixes=(f"{_V1}/billing", f"{_V1}/invoices", f"{_V1}/subscriptions"),
        reason="платёжные данные клиента не входят в делегированный доступ",
    ),
    ForbiddenRule(
        prefixes=(f"{_V1}/privacy/export", f"{_V1}/exports", f"{_V1}/reports/export"),
        reason=(
            "массовая выгрузка персональных данных из-под чужого имени не даёт "
            "ответа на вопрос, кто на самом деле унёс данные"
        ),
    ),
    ForbiddenRule(
        prefixes=(
            f"{_V1}/admin",
            f"{_V1}/api-tokens",
            f"{_V1}/webhooks",
            f"{_V1}/settings/security",
        ),
        reason=(
            "настройки безопасности и ключи доступа переживут выход из "
            "контекста и останутся работать уже без всякого следа"
        ),
    ),
    ForbiddenRule(
        prefixes=(f"{_V1}/",),
        methods=frozenset({"DELETE"}),
        reason=(
            "удаление не оставляет следа правки — остаётся только пропавшая "
            "запись, и разобраться, кто и зачем её убрал, уже нечем"
        ),
    ),
)


def _as_utc(value: datetime) -> datetime:
    """SQLite отдаёт время без часового пояса; сравнение с aware падает."""

    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def session_expires_at(started_at: datetime) -> datetime:
    """Когда работа «от имени» перестанет действовать."""

    return _as_utc(started_at) + CONTEXT_TTL


def session_seconds_left(*, started_at: datetime, now: datetime) -> int:
    """Сколько секунд осталось. Никогда не отрицательное — это счётчик для человека."""

    left = (session_expires_at(started_at) - _as_utc(now)).total_seconds()
    return max(0, int(left))


def ensure_session_active(
    *, started_at: datetime, ended_at: datetime | None, now: datetime
) -> None:
    """Проверить, что контекст ещё действует."""

    if ended_at is not None and _as_utc(ended_at) <= _as_utc(now):
        raise ImpersonationExpired("Работа от имени клиента завершена. Войдите в контекст заново.")
    if session_expires_at(started_at) <= _as_utc(now):
        raise ImpersonationExpired(
            "Срок работы от имени клиента истёк (60 минут). "
            "Войдите в контекст заново, если работа продолжается."
        )


def ensure_action_allowed(*, method: str, path: str) -> None:
    """Проверить, что действие вообще разрешено имперсонатору."""

    if path.startswith(_ALWAYS_ALLOWED):
        return
    for rule in FORBIDDEN_IN_CONTEXT:
        if rule.matches(method=method, path=path):
            raise ForbiddenInContext(
                f"Действие запрещено при работе от имени клиента: {rule.reason}. "
                "Выйдите из контекста и повторите под своей ролью."
            )
