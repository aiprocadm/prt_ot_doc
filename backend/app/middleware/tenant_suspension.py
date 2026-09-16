"""OPS-72, разд. 72.1: приостановка арендатора — «только чтение», а не запертая дверь.

ТЗ в карте жизненного цикла пишет прямо: «Приостановка | Неоплата / пауза →
**safe read-only, данные сохранены**» — и сам же помечает эту строку как
«Частично».

ЧТО БЫЛО. Выключатель подписки (`is_active = false`) означал ПОЛНУЮ блокировку:
``TENANT_BLOCKED``, 403 на любой запрос. Клиент с просроченным счётом не мог ни
посмотреть свои данные, ни выгрузить их, ни даже войти. Это противоречит сразу
трём вещам:

* **ТЗ разд. 72.1** — требуется режим чтения, а не отказ;
* **152-ФЗ и разд. 72.2** — право забрать свои данные не зависит от того,
  оплачен ли следующий месяц;
* **собственному коду платформы** — для клиентов ПРИОСТАНОВЛЕННОГО ПАРТНЁРА
  режим чтения уже сделан (`middleware/reseller_suspension.py`), и там прямо
  записано: «заблокированный клиент не может даже забрать свои данные, и
  отключение партнёра превратилось бы в захват данных его клиентов». Ровно то
  же самое происходило при прямой приостановке — только чинили это лишь для
  чужого простоя, а для своего нет.

РЕШЕНИЯ, КОТОРЫЕ ВАЖНЕЕ КОДА.

* **Данные не трогаются.** Приостановка ничего не пишет и не удаляет — это
  требование ТЗ, а не следствие реализации.
* **Проверка стоит только на записи.** Читать можно: GET/HEAD/OPTIONS не платят
  ни одного лишнего запроса.
* **Вход и выгрузка остаются доступны.** Вход — это POST; запри его, и «только
  чтение» станет «нет доступа». Выгрузка и расторжение — тем более: клиент
  обязан иметь возможность забрать данные и уйти.
* **Отказ называет причину словами.** «Запрещено» без объяснения читается как
  поломка: клиент идёт в поддержку, а дело в неоплаченном счёте.

ГРАНИЦА НАЗВАНА. Отдельного состояния «заблокирован за злоупотребление» в
продукте нет — `is_active` описан в коде как «выключатель подписки». Если такое
состояние понадобится, это отдельное решение и отдельный признак, а не
перегрузка этого.
"""

from __future__ import annotations

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.dependencies import _resolve_tenant_slug
from app.api.helpers.request_tenant import path_is_under, resolve_request_tenant

__all__ = ["TENANT_SUSPENDED_READ_ONLY", "TenantSuspensionReadOnlyMiddleware"]

TENANT_SUSPENDED_READ_ONLY = "TENANT_SUSPENDED_READ_ONLY"

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Пути, которые обязаны работать и у приостановленного арендатора.
_ALWAYS_WRITABLE_PREFIXES = (
    # Вход — POST. Без него «только чтение» превратилось бы в «нет доступа».
    "/api/v1/auth",
    # Выгрузка и расторжение: право забрать свои данные не зависит от оплаты.
    "/api/v1/offboarding",
)


class TenantSuspensionReadOnlyMiddleware(BaseHTTPMiddleware):
    """Приостановленный арендатор читает, но не пишет."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            request.method.upper() not in _MUTATING_METHODS
            or not path.startswith("/api/v1")
            or path_is_under(path, _ALWAYS_WRITABLE_PREFIXES)
        ):
            return await call_next(request)

        identifier = _resolve_tenant_slug(request)
        if not identifier:
            return await call_next(request)

        tenant = await resolve_request_tenant(request, identifier)
        if tenant is None or tenant.is_active:
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": TENANT_SUSPENDED_READ_ONLY,
                    "type": "subscription",
                    "message": (
                        "Подписка приостановлена: данные доступны только на "
                        "чтение и сохранены полностью. Вход и выгрузка данных "
                        "работают как обычно."
                    ),
                }
            },
        )
