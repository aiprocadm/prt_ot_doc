"""SEC-68, разд. 68.1: ключ от чужих документов не ходит в адресе страницы.

ТЗ в таблице угроз пишет прямо: «утечка через Referer/логи/историю → короткий
срок жизни; одноразовость где возможно; **токен не в query**, а лучше в
теле/заголовке».

Адрес страницы — самое дырявое место, какое можно выбрать для ключа: он
попадает в журналы сервера, в историю браузера, в закладки и в заголовок
Referer при переходе на любой внешний ресурс.

ЧТО БЫЛО ДО СРЕЗА-213. Обмен ссылки на короткоживущий сеанс уже существовал, и
в его описании было написано, что после обмена токен в адресе не фигурирует. Но
ручки портала ПРОДОЛЖАЛИ принимать `?token=` — то есть обменивать было МОЖНО, а
не ОБЯЗАТЕЛЬНО. Мера, которую можно обойти, мерой не является.

ЧТО СТАЛО. Ссылочный токен принимается в адресе ровно у двух ручек обмена
(`/portal/otp` и `/portal/session`) — туда человек и приходит по ссылке из
письма. У всех остальных ручек портала — только заголовок `X-Portal-Token` или
сеансовый `X-Portal-Session`.

Проверка идёт ПО ЖИВОМУ ПРИЛОЖЕНИЮ (какие параметры объявлены у ручек), а не по
тексту исходника: текстовый поиск не отличил бы объявленный параметр от
упомянутого в комментарии.
"""

from __future__ import annotations

import pytest
from fastapi.routing import iter_route_contexts

from app.api import create_app

#: Ручки обмена: сюда человек приходит ПО ССЫЛКЕ ИЗ ПИСЬМА, и адрес — его
#: единственный способ предъявить билет. Дальше портал ходит заголовком.
EXCHANGE_PATHS = {"/portal/otp", "/portal/session"}


def _portal_routes():
    """Живые ручки портала с ЭФФЕКТИВНЫМИ путями.

    Обычный ``app.routes`` их не покажет: роутеры подключаются лениво, и в
    списке верхнего уровня лежат группы без развёрнутых путей (записанная
    грабля репозитория). Развёрнутый список даёт ``iter_route_contexts``.
    """

    app = create_app()
    for context in iter_route_contexts(app.routes):
        route = getattr(context, "route", context)
        path = getattr(context, "path", None) or getattr(route, "path", "")
        if "/portal" not in path or not hasattr(route, "dependant"):
            continue
        yield path, route


def _query_param_names(route) -> set[str]:
    """Все параметры адреса ручки — ВКЛЮЧАЯ спрятанные в зависимостях.

    Первая версия смотрела только верхний уровень (`route.dependant`) и
    МУТАЦИЯ НЕ ПОКРАСНЕЛА: у портала приём токена объявлен не в самой ручке, а
    в её зависимости `_portal_auth`, и до неё разбор не доходил. Сторож, не
    прошедший поломку, доказывает только собственную зелёность.
    """

    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        names.update(param.name for param in dep.query_params)
        stack.extend(dep.dependencies)
    return names


def test_разбор_находит_ручки_портала() -> None:
    """Самопроверка: пустой список означал бы зелёный тест ни о чём."""

    paths = {path for path, _ in _portal_routes()}
    assert paths, "разбор не нашёл ни одной ручки портала — он потерял область"
    assert any(
        path.endswith("/session") for path in paths
    ), "не найдена ручка обмена ссылки на сеанс — разбор смотрит не туда"


def test_токен_в_адресе_принимают_только_ручки_обмена() -> None:
    """ГЛАВНОЕ. Ключ в адресе — только там, где человек приходит по ссылке."""

    offenders = []
    for path, route in _portal_routes():
        if any(path.endswith(tail) for tail in EXCHANGE_PATHS):
            continue
        if "token" in _query_param_names(route):
            offenders.append(path)

    assert not offenders, (
        "ссылочный токен принимается в АДРЕСЕ у ручек: "
        f"{sorted(offenders)}. Адрес утекает через журналы, историю браузера и "
        "Referer (разд. 68.1). Ссылку надо обменивать на сеанс "
        "(POST /portal/session), а дальше ходить заголовком X-Portal-Session."
    )


@pytest.mark.parametrize("tail", sorted(EXCHANGE_PATHS))
def test_ручки_обмена_принимают_ссылку_из_письма(tail: str) -> None:
    """Обратная сторона: ссылка из письма обязана работать.

    Без этой половины «починкой» можно было бы объявить запрет везде — и
    сломать единственный способ клиента войти.
    """

    for path, route in _portal_routes():
        if path.endswith(tail):
            assert "token" in _query_param_names(route), (
                f"ручка обмена {path} перестала принимать ссылку из письма — "
                "клиент не сможет войти вообще"
            )
            return
    raise AssertionError(f"ручка {tail} не найдена")
