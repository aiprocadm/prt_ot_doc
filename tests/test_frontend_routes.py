"""Сторож: ссылки витрины ведут на объявленные маршруты (срез-155).

ЗАЧЕМ. Сверка сопоставила все ссылки с литеральным путём (`to=…`,
`navigate(…)`) со списком маршрутов роутера и нашла обещание, которое не
выполняется: на последнем шаге мастера документов кнопка «Открыть
согласование / подпись» вела на `/approvals`, а такого маршрута нет —
объявлены только `/approvals/inbox` и `/approvals/outbox`. Неизвестный путь
перехватывает `path="*"` и молча уводит человека на посадочную страницу: не
ошибка, но и не то, что обещала кнопка, и понять случившееся нельзя.

Это тот же класс, что сторож путей API (`test_frontend_api_paths.py`), но с
другой стороны: там витрина звала несуществующую ручку, здесь — ведёт на
несуществующий экран.

СРЕЗ-156 расширил область. Прежняя проверка видела только ссылки в разметке
(`to=`, `navigate(`) и пропустила пути, записанные ДАННЫМИ: пункты меню
(`to:` в объектах) и карты переходов рабочего стола
(`utils/workspaceNavigation.ts`). Именно там нашлись три ссылки на
`/contracts` — маршрута с таким путём нет, и человек с дашборда молча уезжал
на посадочную страницу: переход к задаче по договору, карточка договора и
подсказка блокера «истекли договоры».

КАК СВЕРЯЕТСЯ. Маршруты собираются из `frontend/src/router`: абсолютные
(`path="/x"`) плюс вложенные относительные (`<Route path="/auth">` с детьми
`login`/`signup` даёт `/auth/login`, `/auth/signup`). Ссылки приводятся к
виду с `{}` вместо подстановок шаблона; сравнение посегментное, параметр
маршрута (`:id`) сходится с любым сегментом. Catch-all `*` намеренно НЕ
считается совпадением: он и есть то место, куда уезжают сломанные ссылки.
"""

from __future__ import annotations

import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTER_DIR = REPO_ROOT / "frontend" / "src" / "router"
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

#: Ссылки, которые намеренно не ведут на маршрут этого приложения.
#: Пусто: внешних и особых ссылок с литеральным путём сейчас нет.
KNOWN_EXTERNAL: dict[str, str] = {}

_ROUTE_RE = re.compile(r'path=(?:"([^"]+)"|\{`([^`]+)`\})')
_LINK_RE = re.compile(r'(?:\bto=|navigate\()\s*\{?\s*(`[^`]*`|"[^"]*"|\'[^\']*\')')


#: Пункт меню и прочая конфигурация: путь записан значением поля `to`.
_OBJECT_LINK_RE = re.compile(r'\bto:\s*(`[^`]*`|"[^"]*")')

#: Карты переходов: файл целиком про навигацию, поэтому все строки «/…» в нём
#: — это пути ЭКРАНОВ. В других файлах так считать нельзя: там такие же
#: строки бывают путями ручек API.
NAVIGATION_MAPS = ("frontend/src/utils/workspaceNavigation.ts",)
_MAP_PATH_RE = re.compile(r'(?:return|:)\s*(`/[^`]*`|"/[^"]*")')


def _normalize(path: str) -> tuple[str, ...]:
    path = path.split("?")[0].split("#")[0]
    path = re.sub(r"\$\{[^}]*\}", "{}", path)
    path = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", path)
    return tuple(segment for segment in path.strip("/").split("/") if segment)


def _declared_routes() -> set[tuple[str, ...]]:
    """Пути маршрутов, включая вложенные относительные."""

    routes: set[tuple[str, ...]] = set()
    for file in sorted(ROUTER_DIR.rglob("*.ts*")):
        text = file.read_text(encoding="utf-8")
        absolute: list[str] = []
        for match in _ROUTE_RE.finditer(text):
            value = match.group(1) or match.group(2)
            if value == "*":
                continue
            if value.startswith("/"):
                absolute.append(value)
                routes.add(_normalize(value))
            else:
                # Относительный путь ребёнка: его родитель — ближайший
                # объявленный выше абсолютный путь в том же файле.
                parent = absolute[-1] if absolute else ""
                routes.add(_normalize(f"{parent}/{value}"))
        for match in re.finditer(r'path:\s*"(/[^"]+)"', text):
            routes.add(_normalize(match.group(1)))
    return routes


def _links() -> dict[str, set[str]]:
    links: dict[str, set[str]] = {}
    for file in list(FRONTEND_SRC.rglob("*.tsx")) + list(FRONTEND_SRC.rglob("*.ts")):
        if ".test." in file.name or "__tests__" in file.parts or "router" in file.parts:
            continue
        text = file.read_text(encoding="utf-8")
        rel = str(file.relative_to(REPO_ROOT))
        patterns = [_LINK_RE, _OBJECT_LINK_RE]
        if rel in NAVIGATION_MAPS:
            patterns.append(_MAP_PATH_RE)
        for pattern in patterns:
            for match in pattern.finditer(text):
                raw = match.group(1)[1:-1]
                raw = re.sub(r"\$\{[^}]*\}", "{}", raw)
                if not raw.startswith("/"):
                    continue
                target = raw.split("?")[0].split("#")[0] or "/"
                links.setdefault(target, set()).add(rel)
    return links


def _matches(link: tuple[str, ...], route: tuple[str, ...]) -> bool:
    if len(link) != len(route):
        return False
    return all(a == b or a == "{}" or b == "{}" for a, b in zip(link, route))


def _broken() -> dict[str, set[str]]:
    routes = _declared_routes()
    broken: dict[str, set[str]] = {}
    for link, files in _links().items():
        if link in KNOWN_EXTERNAL:
            continue
        segments = _normalize(link)
        if not segments:  # ссылка на корень — он объявлен индексом
            continue
        if not any(_matches(segments, route) for route in routes):
            broken[link] = files
    return broken


def test_маршруты_собрались() -> None:
    routes = _declared_routes()
    assert len(routes) > 50, f"маршрутов найдено всего {len(routes)} — проверка потеряла область"
    # Вложенные пути обязаны склеиваться: иначе сторож пропустит ссылку на вход.
    assert ("auth", "login") in routes
    assert ("auth", "signup") in routes


def test_ссылки_витрины_ведут_на_объявленные_маршруты() -> None:
    links = _links()
    assert len(links) > 40, f"ссылок найдено всего {len(links)} — проверка потеряла область"
    # Число ссылок — слабый признак; область держат три источника, и каждый
    # проверяется своим образцом: разметка, пункт меню, карта переходов.
    sources = {file for files in links.values() for file in files}
    assert "/dashboard" in links, "не читаются пункты меню (`to:` в объектах)"
    assert any(
        path in sources for path in NAVIGATION_MAPS
    ), "не читаются карты переходов рабочего стола"
    assert "/crm-finance" in links, "не читается путь экрана из карты переходов"

    broken = _broken()
    assert not broken, (
        "ссылки ведут на несуществующие маршруты (человек молча уезжает "
        "на посадочную страницу по catch-all):\n"
        + "\n".join(f"  {link} — {', '.join(sorted(files))}" for link, files in sorted(broken.items()))
    )
