"""BIZ-49 срез-10 (Доп. №3, разд. 63.2): запреты при работе «от имени клиента».

ТЗ прямо перечисляет, что имперсонатору запрещено ДАЖЕ в контексте клиента:
менять пароли и 2FA, платёжные данные, массово выгружать персональные данные,
удалять данные и трогать настройки безопасности.

Проверка стоит здесь, а не в обработчиках, по одной причине: расставленная
руками, она забывается ровно на том роуте, где нужнее всего, и промах никак не
проявляется — отказа-то нет, всё «работает». Список запретов объявлен один раз
в правилах домена (``domains/managed_clients/impersonation.py``), а этот слой
только применяет его ко входящему запросу.

Проверка срабатывает исключительно при наличии заголовка ``X-Managed-Client``:
обычная работа специалиста под своей ролью не должна платить за это ничем.
"""

from __future__ import annotations

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.dependencies_managed_client import CLIENT_CONTEXT_HEADER
from app.core.errors import api_problem_detail
from app.domains.managed_clients.impersonation import ForbiddenInContext, ensure_action_allowed

__all__ = ["IMPERSONATION_FORBIDDEN_CODE", "ImpersonationGuardMiddleware"]

IMPERSONATION_FORBIDDEN_CODE = "MANAGED_CLIENT_ACTION_FORBIDDEN"


class ImpersonationGuardMiddleware(BaseHTTPMiddleware):
    """Отказать в опасном действии, пока специалист работает от имени клиента."""

    async def dispatch(self, request: Request, call_next):
        if not request.headers.get(CLIENT_CONTEXT_HEADER):
            return await call_next(request)

        try:
            ensure_action_allowed(method=request.method, path=request.url.path)
        except ForbiddenInContext as exc:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": api_problem_detail(
                        code=IMPERSONATION_FORBIDDEN_CODE,
                        message=str(exc),
                        error_type="managed_clients",
                    )
                },
            )
        return await call_next(request)
