"""Арендатор запроса, найденный один раз на запрос.

Проверки в middleware ходят за одной и той же строкой арендатора: режим
«только чтение» офбординга (OPS-72) и каскадная приостановка партнёра
(BIZ-52 разд. 52.1). Каждая своим запросом в базу — это лишний поход на КАЖДЫЙ
изменяющий запрос, и с добавлением третьей проверки цена растёт линейно.

Результат кладётся в ``request.state`` — область жизни ровно одного запроса,
поэтому «кэш» здесь не может протухнуть: заголовок арендатора внутри запроса не
меняется.
"""

from __future__ import annotations

from fastapi import HTTPException
from starlette.requests import Request

from app.api.dependencies import _fetch_tenant_by_identifier
from app.models.models import Tenant

__all__ = ["path_is_under", "resolve_request_tenant"]


def path_is_under(path: str, prefixes: tuple[str, ...]) -> bool:
    """Лежит ли путь под одним из префиксов — по ГРАНИЦЕ сегмента.

    Обычный ``startswith`` здесь опасен: список исключений режима «только
    чтение» содержит ``/api/v1/auth``, и путь ``/api/v1/authorizations`` попал
    бы в исключения просто потому, что начинается с тех же букв. Сегодня такой
    ручки нет, но появись она завтра — она молча обошла бы защиту, и заметить
    это можно было бы только по последствиям.
    """

    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)

_STATE_ATTR = "_resolved_request_tenant"
#: Отдельная метка «уже искали и не нашли». Без неё ненайденный арендатор
#: означал бы «в кэше пусто» и приводил бы к повторному запросу в базу на каждой
#: следующей проверке — ровно в случае, который встречается чаще всего под
#: перебором чужих идентификаторов.
_MISS = object()


async def resolve_request_tenant(request: Request, identifier: str) -> Tenant | None:
    """Найти арендатора запроса, сходив в базу не более одного раза.

    ``None`` означает «неизвестный или неактивный»: разбираться с этим —
    не дело проверок, обычный обработчик ответит своим 404/403.
    """

    cached = getattr(request.state, _STATE_ATTR, None)
    if cached is _MISS:
        return None
    if cached is not None:
        return cached

    try:
        tenant = await _fetch_tenant_by_identifier(identifier)
    except HTTPException:
        setattr(request.state, _STATE_ATTR, _MISS)
        return None

    setattr(request.state, _STATE_ATTR, tenant)
    return tenant
