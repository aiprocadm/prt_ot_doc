"""BIZ-52 срез-3 (разд. 52.1): приостановка партнёра — «только чтение» у клиентов.

ТЗ: «Каскадное отключение: приостановка reseller'а безопасно приостанавливает
его клиентов (safe read-only), но не удаляет данные».

СВЕРКА нашла две вещи, и обе — не «не сделано», а «сделано наоборот»:

1. Приостановка вообще не каскадировала. ``is_active`` — признак ОДНОЙ строки;
   партнёра выключали, а его клиенты продолжали работать как ни в чём не бывало,
   хотя услуга уже не оплачена.
2. Приостановка означает полную блокировку (``TENANT_BLOCKED``, 403 в
   ``middleware/tenant.py``), а ТЗ просит «safe read-only». Разница не
   косметическая: заблокированный клиент не может даже забрать свои данные, и
   отключение партнёра превратилось бы в захват данных его клиентов.

Решения, которые важнее кода:

* **Состояние ВЫЧИСЛЯЕТСЯ, а не хранится.** Никакой пометки «мой партнёр
  приостановлен» на клиентах не ставится. Проставь её каскадной записью — и
  понадобится обратный каскад при возобновлении, бэкфилл для существующих строк
  и ремонт после каждого сбоя на середине. Здесь же возобновление партнёра
  снимает режим у всех его клиентов мгновенно и без единой записи в базу.
* **Данные не удаляются и не меняются.** Проверка ничего не пишет — это прямое
  требование ТЗ, а не следствие реализации.
* **Проверка стоит только на записи.** «Только чтение» означает, что читать
  можно: GET/HEAD/OPTIONS не платят ни одного лишнего запроса.
* **Вход и выгрузка остаются доступны.** Логин — это POST; запри его, и
  «только чтение» станет «нет доступа», а клиент не заберёт собственные данные.
  То же с офбордингом: клиент чужого простоя не выбирал и обязан иметь
  возможность уйти.
* **Отказ объясняет причину и виновника.** «Запрещено» без причины читается как
  поломка: клиент пойдёт в поддержку и услышит «у нас всё работает». Здесь он
  сразу знает, что вопрос к обслуживающей компании.
"""

from __future__ import annotations

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.dependencies import _resolve_tenant_slug
from app.api.helpers.request_tenant import path_is_under, resolve_request_tenant
from app.db.session import AsyncSessionLocal
from app.models.models import Tenant

__all__ = ["ResellerSuspensionReadOnlyMiddleware", "RESELLER_SUSPENDED_READ_ONLY"]

RESELLER_SUSPENDED_READ_ONLY = "RESELLER_SUSPENDED_READ_ONLY"

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Пути, которые обязаны работать и при приостановленном партнёре.
_ALWAYS_WRITABLE_PREFIXES = (
    # Вход — POST. Без него «только чтение» превратилось бы в «нет доступа».
    "/api/v1/auth",
    # Выгрузка и расторжение: клиент не выбирал простой партнёра и не должен
    # оказаться заперт вместе со своими данными.
    "/api/v1/offboarding",
)


class ResellerSuspensionReadOnlyMiddleware(BaseHTTPMiddleware):
    """Запретить запись клиенту, чей партнёр приостановлен."""

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
        # Прямой клиент платформы родителя не имеет — самый частый случай,
        # и он не стоит ни одного запроса к базе.
        if tenant is None or not tenant.parent_id:
            return await call_next(request)

        parent_name = await self._suspended_parent_name(str(tenant.parent_id))
        if parent_name is None:
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": {
                    "code": RESELLER_SUSPENDED_READ_ONLY,
                    "type": "reseller",
                    "message": (
                        f"Обслуживающая компания «{parent_name}» временно "
                        "приостановлена: данные доступны только на чтение. "
                        "Выгрузка и вход работают как обычно."
                    ),
                    "reseller_name": parent_name,
                }
            },
        )

    @staticmethod
    async def _suspended_parent_name(parent_id: str) -> str | None:
        """Название партнёра, если он приостановлен, иначе ``None``.

        Возвращается именно НАЗВАНИЕ, а не признак: сообщение об отказе без
        имени виновника заставляет клиента гадать, к кому идти.
        """

        async with AsyncSessionLocal(
            tenant="public", include_public=False, create_schema=False
        ) as session:
            parent = await session.get(Tenant, parent_id)
            if parent is None or parent.is_active:
                return None
            return str(parent.name)
