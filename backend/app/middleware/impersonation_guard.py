"""BIZ-49 (Доп. №3, разд. 63.2): запреты при работе от имени клиента.

ТЗ прямо перечисляет, что имперсонатору запрещено ДАЖЕ в контексте клиента:
менять пароли и 2FA, платёжные данные, массово выгружать персональные данные,
удалять данные и трогать настройки безопасности.

Проверка стоит здесь, а не в обработчиках, по одной причине: расставленная
руками, она забывается ровно на том роуте, где нужнее всего, и промах никак не
проявляется — отказа-то нет, всё «работает». Список запретов объявлен один раз
в правилах домена (``domains/managed_clients/impersonation.py``), а этот слой
только применяет его ко входящему запросу.

## ДЫРА, КОТОРУЮ ЗАКРЫЛ СРЕЗ ВХОДА В КОНТУР DEDICATED-КЛИЕНТА

Раньше сторож срабатывал ТОЛЬКО при заголовке ``X-Managed-Client``. Этого
хватало, пока работа «от имени» шла внутри пространства аутсорсера. Но у
Dedicated-клиента специалист входит в ЕГО контур с отдельным токеном, и
заголовка там нет — то есть вход в контур сам по себе стал бы обходом всех
запретов разд. 63.2. Поэтому делегированность определяется по заголовку
**или** по метке в самом токене, которую подделать нельзя.

## ПОЧЕМУ ПРОВЕРКА ИДЁТ ОТ ПУТИ, А НЕ ОТ ПРИЗНАКА ДЕЛЕГИРОВАНИЯ

Разбор токена — работа, пусть и небольшая. Опасных путей единицы, а обычных
запросов — все остальные. Поэтому сначала выясняется, задевает ли запрос хоть
один запрет (сравнение строк), и лишь для такого запроса выясняется, кто его
шлёт. Обычная работа специалиста под своей ролью не платит за сторожа ничем.
"""

from __future__ import annotations

import json
from base64 import urlsafe_b64decode

from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.dependencies_managed_client import CLIENT_CONTEXT_HEADER
from app.core.errors import api_problem_detail
from app.domains.managed_clients.delegated_identity import DELEGATED_CLIENT_CLAIM
from app.domains.managed_clients.impersonation import find_forbidden_rule

__all__ = ["IMPERSONATION_FORBIDDEN_CODE", "ImpersonationGuardMiddleware"]

IMPERSONATION_FORBIDDEN_CODE = "MANAGED_CLIENT_ACTION_FORBIDDEN"


def _token_is_delegated(request: Request) -> bool:
    """Несёт ли токен запроса метку работы в контуре клиента.

    ПОДПИСЬ ЗДЕСЬ НЕ ПРОВЕРЯЕТСЯ — И ЭТО ОСОЗНАННО. Ответ этой функции умеет
    только ДОБАВИТЬ запрет, никогда не снять. Подделать токен «с меткой» —
    значит запретить себе лишнее; убрать метку из настоящего токена нельзя, не
    сломав подпись, а сломанную подпись отвергнет проверка прав следом. Зато
    запрет на удаление покрывает весь ``/api/v1``, то есть сюда попадает каждое
    удаление в продукте: полная сверка подписи здесь означала бы вторую
    криптографическую проверку на каждом таком запросе — плату без выгоды.

    Любая беда с разбором — это «не делегированный»: негодный токен всё равно
    отвергнет проверка прав, и делать её работу здесь не нужно.
    """

    header = request.headers.get("authorization") or ""
    scheme, _, raw = header.partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        return False
    parts = raw.strip().split(".")
    if len(parts) != 3:
        return False
    try:
        # base64url без выравнивания: добиваем «=» до кратности четырём.
        body = parts[1]
        payload = json.loads(urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:  # noqa: BLE001 - нечитаемый токен отвергнет проверка прав
        return False
    return bool(isinstance(payload, dict) and payload.get(DELEGATED_CLIENT_CLAIM))


class ImpersonationGuardMiddleware(BaseHTTPMiddleware):
    """Отказать в опасном действии, пока специалист работает от имени клиента."""

    async def dispatch(self, request: Request, call_next):
        rule = find_forbidden_rule(method=request.method, path=request.url.path)
        if rule is None:
            return await call_next(request)

        if not request.headers.get(CLIENT_CONTEXT_HEADER) and not _token_is_delegated(request):
            return await call_next(request)

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "detail": api_problem_detail(
                    code=IMPERSONATION_FORBIDDEN_CODE,
                    message=(
                        f"Действие запрещено при работе от имени клиента: {rule.reason}. "
                        "Выйдите из контекста и повторите под своей ролью."
                    ),
                    error_type="managed_clients",
                )
            },
        )
