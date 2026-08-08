"""BIZ-49 срез-7 (разд. 49.3): работа «в контексте клиента» (impersonation).

Чистые правила без БД. ТЗ: «Impersonation / работа в контексте клиента — с
ОБЯЗАТЕЛЬНОЙ пометкой в аудите: кто, от имени какого клиента, что сделал.
Требование ПДн: действия аутсорсера в данных клиента всегда трассируемы».

Два решения, которые здесь важнее остального:

* **отказ вместо тихого игнорирования.** Если специалист заявил контекст
  клиента, а гранта нет — это ОТКАЗ, а не «работай в своём контексте». Молча
  проигнорировать заголовок значит дать человеку уверенность, что он пишет
  в данные клиента, тогда как он пишет их не туда;
* **грант проверяется на совпадение И пользователя, И клиента.** Грант коллеги
  или грант на другого клиента — не мой доступ; без этой проверки доступ
  «переползает» между строками матрицы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domains.managed_clients.access import AccessGrant, grant_allows, is_grant_active
from app.domains.managed_clients.lifecycle import ManagedClientMode

__all__ = [
    "ON_BEHALF_OF_KEY",
    "ClientContext",
    "ClientContextDenied",
    "active_client_context",
    "build_context_audit_meta",
    "on_behalf_of_stamp",
    "resolve_client_context",
]

#: Ключ, под которым пометка «от имени клиента» лежит в ``details`` аудита.
#: Одно имя на весь код: по нему и пишут, и ищут в журнале доступа.
ON_BEHALF_OF_KEY = "on_behalf_of"


class ClientContextDenied(PermissionError):
    """Контекст клиента заявлен, но не подтверждён грантом."""


@dataclass(frozen=True)
class ClientContext:
    """Подтверждённый контекст: специалист работает ОТ ИМЕНИ клиента.

    Режим и организация клиента приезжают вместе с контекстом (срез-9): без
    них каждый роут, которому нужен фильтр по данным, лез бы за ними в базу
    отдельным запросом — на каждый запрос страницы.
    """

    user_id: str
    client_id: str
    client_name: str
    all_modules: bool
    modules: tuple[str, ...]
    mode: ManagedClientMode = ManagedClientMode.LIGHTWEIGHT
    company_id: str | None = None

    def allows(self, module: str) -> bool:
        return self.all_modules or module in self.modules


def resolve_client_context(
    *,
    grant: AccessGrant | None,
    user_id: str,
    client_id: str,
    client_name: str,
    now: datetime,
    mode: ManagedClientMode = ManagedClientMode.LIGHTWEIGHT,
    company_id: str | None = None,
) -> ClientContext:
    """Подтвердить заявленный контекст клиента или отказать."""

    if grant is None:
        raise ClientContextDenied("Нет доступа к этому клиенту")
    if grant.user_id != user_id:
        raise ClientContextDenied("Доступ выдан другому специалисту")
    if grant.client_id != client_id:
        raise ClientContextDenied("Доступ выдан к другому клиенту")
    if not is_grant_active(grant, now=now):
        raise ClientContextDenied("Доступ к клиенту отозван")

    return ClientContext(
        user_id=user_id,
        client_id=client_id,
        client_name=client_name,
        all_modules=grant.all_modules,
        modules=tuple(grant.modules),
        mode=mode,
        company_id=company_id,
    )


def on_behalf_of_stamp(context: ClientContext) -> dict[str, Any]:
    """Короткая пометка «X от имени Y» для ЛЮБОЙ записи аудита (разд. 63.2).

    ТЗ требует, чтобы «каждое действие было помечено X от имени Y». Пометка
    отдельным событием этого не даёт: читающий запись «специалист изменил
    карточку» не видит рядом ничего, а связать её с входом в контекст можно
    только вручную по времени. Поэтому метка едет ВНУТРИ самой записи.

    Только JSON-совместимые значения — уходит в JSON-поле аудита.
    """

    return {
        "actor_user_id": context.user_id,
        "managed_client_id": context.client_id,
        "managed_client_name": context.client_name,
    }


def build_context_audit_meta(
    context: ClientContext, *, action: str, method: str | None = None
) -> dict[str, Any]:
    """Пометка аудита: кто, от имени какого клиента, что сделал.

    ``method`` нужен журналу доступа (разд. 63.2): в ответе на вопрос клиента
    «кто трогал мои данные» чтение и запись — разные ответы, а один только
    путь их не различает.

    Значения только JSON-совместимые — пометка уходит в JSON-поле аудита.
    """

    return {
        "on_behalf_of_client": True,
        "actor_user_id": context.user_id,
        "managed_client_id": context.client_id,
        "managed_client_name": context.client_name,
        "action": action,
        "method": method,
        "all_modules": context.all_modules,
        "modules": list(context.modules),
    }


def active_client_context() -> ClientContext | None:
    """Контекст клиента текущего запроса — или ``None`` вне запроса.

    Читается из состояния запроса, куда его кладёт зависимость после проверки
    гранта. Своего хранилища домен не заводит: у аудита нет и не может быть
    параметра «а это от имени клиента» — его забыли бы ровно там, где он нужен.
    """

    from app.core.request_context import get_current_request  # noqa: PLC0415 - цикл импорта

    request = get_current_request()
    if request is None:
        return None
    context = getattr(request.state, "managed_client_context", None)
    return context if isinstance(context, ClientContext) else None


def context_allows_module(
    context: ClientContext, module: str, *, grant: AccessGrant, now: datetime
) -> bool:
    """Проверка модуля через тот же предикат, что и матрица доступа."""

    return grant_allows(grant, module=module, now=now)
